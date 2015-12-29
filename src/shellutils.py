import os, os.path, importlib
import shutil, signal, subprocess, json, sys
import platform
if platform.system() == 'Linux':
   import pwd, getpass, grp
from multiprocessing import Process

def mkdir(name):
   """recursively create dirs (like mkdir -p)"""
   #os.mkdir(name) #make one directory
   #exists_ok prevents errors when dir already exists
   os.makedirs(name, exist_ok=True)

def ls(path):
   return os.listdir(path)

def is_file(path):
   return os.path.isfile(path)

def is_dir(path):
   return os.path.isdir(path)

def is_link(path):
   return os.path.islink(path)

def is_mount_point(path):
   return os.path.ismount(path)

def rm(path):
   """Removes files and directories"""
   if is_dir(path):
      #os.removedirs(path) #only works for empty
      shutil.rmtree(path)
   elif is_file(path) or is_link(path):
      os.remove(path)
   else:
      if file_exists(path):
         raise Exception('Trying to remove unknown file type')

def cp(src, dst):
   if is_dir(src):
      shutil.copytree(src, dst)
   elif is_file(src):
      shutil.copy(src, dst)

def ln(target, name):
   os.symlink(target, name)


##PATH STUFF
def cwd():
   return os.getcwd()

#dirname(f) gets directory of f
#realpath(path) removes symbolic links
#normpath(path) 'A//B', 'A/B/', 'A/foo/../B' => 'A/B'
#abspath(path) same as normpath but also prepends cwd()

#say you have app/src/main.py. To get path of project directory (app)
#from main.py you can use get_relative_path(__file__, '..')
def get_abs_path_relative_to(current_file, *relative_path):
   from os.path import abspath, dirname, realpath, join
   if relative_path is None:
      relative_path = ['']
   return abspath(join(dirname(realpath(current_file)), *relative_path))
##END OF RANDOM PATH STUFF

def file_exists(filePath):
   return (filePath is not None) and os.path.exists(filePath)

def check_paths(*paths):
   bad = []
   for p in paths:
      if file_exists(p) is False:
         bad.append(p)
   return bad

def write_file(filePath, data, binary=False):
   flags = 'w'
   if binary:
      flags = 'wb'
   with open(filePath, flags) as f:
      return f.write(data)

def read_file(filePath, nBytes=None, binary=False, createIfNeeded=False):
   if file_exists(filePath):
      flags = 'r'
      if binary:
         flags = 'rb'
      with open(filePath, flags) as f:
         if nBytes:
            return f.read(nBytes)
         else:
            return f.read()
   elif filePath and createIfNeeded:
      assert not nBytes
      file(filePath, 'w').close()
   return None

def write_json(path, json_data):
   write_file(path, json.dumps(json_data) + '\n')

def read_json(path):
   if path:
      data = read_file(path)
      if data:
         return json.loads(data)
   return None

def get_file_size(filename):
   "Get the file size by seeking end"
   fd = os.open(filename, os.O_RDONLY)
   try:
      return os.lseek(fd, 0, os.SEEK_END)
   finally:
      os.close(fd)
   return -1

def parse_mtab():
   mounts = []
   mtab_str = read_file('/etc/mtab').strip()
   entries = mtab_str.split('\n')
   for entry in entries:
      lst = entry.split(' ')
      #http://serverfault.com/questions/267609/how-to-understand-etc-mtabm
      item = {
         'mount-device'    : lst[0], #current device in /dev/sd*[n]
         'mount-point'     : lst[1], #where it's mounted
         'file-system'     : lst[2],
         'mount-options'   : lst[3],
         'dump-cmd'        : lst[4],
         'fsck-order-boot' : lst[5]
      }
      mounts.append(item)
   return mounts

#works for drives and partitions
def get_mount_point(drive):
   mounts = parse_mtab()
   for device in mounts:
      if device['mount-device'] == drive:
         return device['mount-point']
   return None

#new thread non-block
def func_thread(callback):
   p = Process(target=callback).start()

#non-blocking
def exec_prog(command):
   if type(command) is list:
      args = command
   else:
      args = command.split()
   p = Process(target=lambda:subprocess.call(args))
   p.start()

def exec_sudo(cmd):
   return exec_get_stdout('gksudo %s' % cmd)

#TODO: use arrays instead of map/dict?
def exec_prog_with_env(command, envBindings):
   args = command.split()
   my_env = os.environ.copy() #vs os.environ
   for name in envBindings:
      my_env[name] = envBindings[name]

   def subProc():
      #TODO: why shell == True???
      subprocess.Popen(args, env=my_env, shell=True)

   Process(target=subProc).start()

def get_random_byte_str(length=15):
    return read_file('/dev/urandom', length, binary=True)

#TODO: maybe replace with python version
def get_random(max_num=None):
   rand_len = get_random_byte_str(1)[0] % 10 + 1
   rand_str = get_random_byte_str(rand_len)
   total = 0
   i = 1
   for x in rand_str:
      total += x * i
      i*= 10
   if max_num is None:
      return total
   return total % (max_num + 1)

#import pwd, os, getpass, grp
#TODO: get user groups

def get_current_user_id():
   return os.getuid()

def get_current_user_name():
   return getpass.getuser()

def get_user_info(usrname=None, usrid=None):
   info = None
   if usrname is not None and usrid is not None:
      msg = "Calling get_user_info with usrid and usrname but only 1 allowed"
      raise Exception(msg)
   if usrname is not None:
      info = pwd.getpwnam(usrname)
   elif usrid is not None:
      info = pwd.getpwuid(usrid)
   else:
      info = pwd.getpwuid(get_current_user_id())
   return info

def get_user_id(usrname=None, usrid=None):
   return get_user_info(usrname, usrid)[2]
def get_user_group_id(usrname=None, usrid=None):
   return get_user_info(usrname, usrid)[3]
def get_user_home_dir(usrname=None, usrid=None):
   return get_user_info(usrname, usrid)[5]
def get_user_shell(usrname=None, usrid=None):
   return get_user_info(usrname, usrid)[6]

#unix user groups
def get_group_db():
   return grp.getgrall()

def get_group_by_name(name, grpdb=None):
   """Given name of group, return it's internal structure."""
   if grpdb is None:
      grpdb = get_group_db()
   for group in grpdb:
      if group.gr_name == name:
         return group
   return None

def get_name_from_group_data(groupdata):
   """Given internal groupdata, get group's name."""
   return groupdata.gr_name

#TODO: check if both are none
#TODO: check if get_group_by_name returns None
def get_group_members(groupname=None, groupdata=None):
   """Returns list of user names in the given group name or group_data that was obtained from get_group_by_name()."""
   if groupdata is None:
      groupdata = get_group_by_name(grpname)
   return groupdata.gr_mem


def get_user_groups(usrname, grpdb=None):
   """Returns list of group names that the user is member of."""
   ret = []

   if grpdb is None:
      grpdb = get_group_db()
   for group in grpdb:
      members = get_group_members(groupdata=group)
      for grp_mem in members:
         if grp_mem == usrname:
            ret.append(get_name_from_group_info(grp_mem))
   return ret

#get password database
def get_password_db():
   return pwd.getpwall()

#end pwd

def reload_module(module):
   """from pycloak import shellutils. shellutils.reload_module(shellutils)"""
   importlib.reload(module)

#blocking, returns output
def exec_get_stdout(command):
   args = command.split()
   task = subprocess.Popen(args, stdout=subprocess.PIPE)
   return task.communicate()

class ProgressBar(object):
    def __init__(self, max_width = 20):
        self.spinner = ['/', '-', '\\', '-']
        self.spinner_tick = 0
        self.max_width = max_width

    def update(self, p, label=""):
        self.spinner_tick += 1
        i = int((p * self.max_width) / 100)
        s = self.spinner[self.spinner_tick % len(self.spinner)]
        bar = "%s%s%s" % ("".join(['='] * i), s, "".join([' '] * (self.max_width - i - 1)))
        sys.stdout.write("\r[%s] %s" % (bar, label))
        sys.stdout.flush()


