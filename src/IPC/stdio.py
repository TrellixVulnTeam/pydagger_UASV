import sys
import time
import json
import traceback
import inspect
import textwrap
from pprint import pprint, pformat
from jsonrpc import JSONRPCResponseManager, dispatcher
from pycloak.events import Event

class StdioClient(object):
   def __init__(self, server):
      self._server = server

   def __getattr__(self, name):

      server = self._server
      def proxymethod(*args, **kwargs):
         if args and len(args) > 0:
            raise NotImplementedError("Only arguments by name are allowed")
         return server.call(name, kwargs)

      return proxymethod

class StdioCom(object):

   def __init__(self, namespace, protocol = "JSONRPC"):
      self.namespace = namespace
      self.run = False
      self._jsonrpc = JSONRPCResponseManager()
      self._send_id=0
      self.protocol = protocol
      self._send_events = {}
      self.on_call_error = Event()
      self.client = StdioClient(self)
      # list of callable members
      methods = [ method for method in dir(self) if callable(getattr(self, method)) ]
      for method in methods:
         # get method intance
         m = getattr(self, method)
         # check if its exposed
         if m and hasattr(m, "exposed"):
            dispatcher[method if not namespace else "%s.%s" % (namespace,method)] = m # add it to jsonrpc methods

   def generate_doc(self, format):
      return self._api_generator(format, "doc")

   def generate_api(self, lang):
      return self._api_generator(lang, "api")

   def _api_generator(self, lang, generator):
      g_start = getattr(self, "_generate_%s_start" % generator)
      g_method = getattr(self, "_generate_%s_method" % generator)
      g_end = getattr(self, "_generate_%s_end" % generator)

      # list of callable members
      methods = [ method for method in dir(self) if callable(getattr(self, method)) ]
      api_src = []
      api_src.append(g_start(lang))
      for method in methods:
         m = getattr(self, method)
         # check if its exposed
         if m and hasattr(m, "exposed"):
            args = [arg for arg in inspect.getargspec(m).args if arg != "self"]
            api_src.append(g_method(lang, method, args, inspect.getdoc(m)))
         elif m and hasattr(m, "exposed_raw"):
            if hasattr(m, "exposed_args"):
               args = m.exposed_args
            else:
               args = [arg for arg in inspect.getargspec(m).args if arg != "self"]
            api_src.append(g_method(lang, method, args, inspect.getdoc(m), m))


      api_src.append(g_end(lang))
      return "\n\n".join(api_src)

   def _generate_api_start(self, lang):
      if lang in ["nodejs"]:
         return """'use strict';
module.exports = (function() {
    var util = require('util');
    var EventEmitter = require('events').EventEmitter;
    var stdio = require("stdio");

    var %(namespace)s = function(bin_path, args) {
        this._transport = new stdio.stdioLib(bin_path, args);
        this._rpc = new stdio.jsonrpc(this._transport, "%(namespace)s");
        var base = this;
        this._rpc.on("connected", function() {
           base.emit("connected");
        });
        this._rpc.on("error", function(error) {
            base.emit("error", error);
        });
    }

    // Inherit event emitter functionality
    util.inherits(onering, EventEmitter);
    
    // Start transport
    onering.prototype.start = function() {
        this._transport.start()
    }
""" % dict(namespace=self.namespace)
      elif lang in ["javascript"]:
         return "var %s = function(rpc) { this._rpc = rpc; }" % self.namespace

      return ""

   def _generate_api_method(self, lang, method, args, doc, raw = None):
      if lang in ["javascript", "nodejs"]:
         space = ""
         if lang == "nodejs":
            space = "    ";
         out = ""
         args_call = []
         for arg in args:
            args_call.append("'%s': %s" % (arg, arg))


         if raw is None:
            body = "return this._rpc.call('%s', {%s});" % (method, ", ".join(args_call))
         else:
            body = raw()

         if doc:
            doc = "%s/**\n%s\n%s */\n" % (space, "\n".join(["%s * %s" % (space, line) for line in doc.splitlines()]), space)
         else:
            doc = ""

         return "%s%s%s.prototype.%s = function(%s) { %s }" % (doc, space, self.namespace, method, ", ".join(args), body)

      return ""

   def _generate_api_end(self, lang):
      if lang == "javascript":
         return ""
      elif lang == "nodejs":
         return """    return %(namespace)s;
}());""" % dict(namespace=self.namespace)

      return ""

   def _generate_doc_start(self, format):

      if format == "html":
         style="""
html, body { width: 100%; height: 100%; padding: 0; margin: 0; }
.method { padding: 0 0 2em 2em; border-bottom: 1px solid #000; }
.method .name { color: green; text-weight: bolder; }
.method .arg { color: red; }
.method .doc { padding-left: 4em; }
"""
         return '<!doctype html><html><head><title>%(namespace)s Documentation</title><style type="text/css">%(style)s</style></head><body><div class="namespace">%(namespace)s</div>' % dict(namespace=self.namespace, style=style)

      return ""

   def _generate_doc_method(self, format, method, args, doc, raw = None):

      if format == "text":
         args_txt = ", ".join(args)
         doc_txt = "\n".join(textwrap.wrap(doc, width=40, initial_indent=' ' * 4, subsequent_indent=' ' * 4))
         #doc_txt = "%s\n" % doc_txt if len(doc_txt) > 0 else ""
         return '%(method)s(%(args)s)\n%(doc)s' % dict(method=method, args=args_txt, doc=doc_txt)

      if format == "html":
         args_txt = ['<span class="arg">%s</span>' % arg for arg in args]
         return '<div class="method"><span class="name">%(method)s</span>(<span class="args">%(args)s</span>)<div class="doc">%(doc)s</div></div>' % dict(method=method, args=", ".join(args_txt), doc=doc)
      return ""

   def _generate_doc_end(self, format):
      if format == "html":
         return """</body>
</html>"""
      return ""

   def start(self):
      """Main stdio loop"""
      self.run = True
      while self.run:
         self._on_idle()
         time.sleep(0.1)

   def stop(self):
      """Stops stdio loop"""
      self.run = False

   def call(self, method, args):
      """Performs rpc methods"""
      evt =dict(on_result=Event(), on_error=Event())
      try:
         package = dict(jsonrpc="2.0", method=method, params=args, id=self._send_id)
         self._send_events["e%s" % self._send_id] = evt 
         self._send(json.dumps(package))
      except:
         self._send_events.pop("e%s" % self._send_id, None)
         return False
      finally:
         self._send_id+=1

      return evt

   def _handle_client_response(self, data):
      """Handles replies from client"""
      if "id" in data:
         # get and remove event if available
         evt = self._send_event.pop("e%s" % data["id"], None)

      if "result" in data:
         if evt and "on_result" in evt:
            try:
               evt["on_result"](data["result"])
            except:
               pass

      elif "error" in data:
         if evt and "on_error" in evt:
            try:
               evt["on_error"](data["error"])
            except:
               pass
         else:
            self.on_call_error(data["error"])

   def _send(self, data):
      sys.stdout.write("%s\n" % data)
      sys.stdout.flush()

   def _send_error(self, code, message, data, id):
      package = dict(jsonrpc="2.0", error=dict(code=code, message=message, data=data), id=id)
      self._send(json.dumps(package))
               
   def _on_idle(self):
      """Handles internal communication parsing"""
      data = None
      try:
         line = sys.stdin.readline()
         if line:
            data = line.strip()
      except:
         pass

      if data:
         if self.protocol == "JSONRPC":
            try:
               data_json = json.loads(data)
            except:
               self._send_error(code=-32700, message="Invalid json data", data=traceback.format_exc(), id=None)
               return

            if "result" in data_json or "error" in data_json:
               self._handle_client_result(data_son)
               return
            
            method = data_json.get("method", None)
            params = data_json.get("params", None)
            id = data_json.get("id", None)

            if method is None or params is None:
               self._send_error(code=-32600, message ="Invalid Request", id=id)
            elif dispatcher.get(method, None) == None:
               self._send_error(code=-32601, message = "Method Not Found", id=id)
            else:
               try:
                  result = dispatcher[method](**params)
                  self._send(json.dumps(dict(jsonrpc="2.0", result=result, id=id)))
               except Exception as ex:
                  exc_type, exc_value, exc_traceback = sys.exc_info()
                  exception_list = traceback.format_stack()
                  
                  self._send_error(code=-32000, message = exc_value, data = "\n".join(exception_list), id=id)
         else:
            print("INVALID PROTOCOL: %s" % line)
            self.run = False

      self.on_idle()
   
   def on_idle(self):
      pass
