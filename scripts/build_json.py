#!/usr/bin/python
# -*- coding: utf-8 -*-

# Part of the Processing project - http://processing.org
# 
#   Copyright (c) 2020 Elie Zananiri
# 
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2
#   as published by the Free Software Foundation.
# 
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
# 
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software Foundation,
#   Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

"""
Reads a configuration file listing direct links to contributions grouped by
category. The config file is formatted using the following style:

    # A comment. Everything after the hash is ignored
    [Library : Sound] # Type of software : category name.
    # Contribution ID \ A url of a library in the sound category
    043 \ http://example.com/libs/soundlib1.txt
    # Contribution ID \ Another url of a library in the sound category
    074 \ http://example.org/libs/soundlib2.txt

    [Library : Vision] # Another category
    012 \ http://example.net/libs/visionlib.txt

After parsing the config file, information on each contribution is retrieved 
from the text files, and the contribution is assumed to be hosted at the same
address as the txt, but with .zip.  For example, visionlib in the example above
would be found at http://example.com/libs/visionlib.zip

This script takes two arguments
  Arg 1: The name of a config file to read from
  Arg 2: The name of a folder to write to. Each contribution will write its data
         to a separate file in that folder. The file will be overwritten if it
         already exists
         
If no arguments are passed, it uses the following defaults
  Arg 1: sources.conf
  Arg 2: .
"""

from sys import argv
from urllib.request import urlopen
from time import localtime, gmtime, strftime
import re
import shutil
import http.client
import sys
import json
import os

class Logger(object):
  def __init__(self):
    self.terminal = sys.stdout
    self.log = open("build.log", "a")

  def __getattr__(self, attr):
    return getattr(self.terminal, attr)

  def write(self, message):
    self.terminal.write(message)
    self.log.write(message)  

  def flush(self):
    pass

sys.stdout = Logger()

def read_exports(f):
  """
  Reads a library's export.txt file and returns a dictionary.
  """
  lines = f.read().decode('utf-8')
  lines = lines.replace("authorList", "authors").replace("category", "categories").replace("compatibleModesList", "modes")
  lines = lines.replace('\r\n', '\n').replace('\r', '\n')
  lines = lines.split('\n')
  
  export_table = {}
  
  for line in lines:
    hash = line.find('#')
    line = line.strip() if hash == -1 else line[:hash]
    if len(line) == 0:
      continue

    equals = line.find('=')
    if equals == -1:
      continue
    
    attr = line[:equals].strip()
    val = line[equals+1:].strip()
    export_table[attr] = val
  
  return export_table

def format_exports(exports):
  """
  Update the dictionary to the new format
  """
  if 'authors' in exports:
    exports['authors'] = [exports['authors']]

  if 'categories' in exports and exports['categories']:
    categories = exports['categories'].split(',')
    for cat in categories:
      cat.strip()
    exports['categories'] = categories
  else:
    exports['categories'] = None
  
  package_java = { }
  package_java['mode'] = 'java'
  package_keys = ['minRevision', 'maxRevision', 'props', 'download']
  for key in package_keys:
    if key in exports:
      package_java[key] = exports[key]
      exports.pop(key)

  exports['packages'] = [ package_java ]

  remove_keys = ['version', 'prettyVersion']
  for key in remove_keys:
    if key in exports:
      exports.pop(key)

  return exports

def write_exports(dirout, exports):
  """
  Writes the given dictionary to a json file
  """
  
  blacklist = ["\\", "/", ":", "*", "?", "\"", "<", ">", "|", "\0"]
  filename = exports['name'].strip()
  filename = "".join(c for c in filename if c not in blacklist)
  filename = "".join(c for c in filename if 31 < ord(c))
  filename = filename.replace(' ', '_')

  filepath = os.path.join(dirout, filename + '.json')
  print('export ' + exports['packages'][0]['props'] + ' to ' + filepath)
  with open(filepath, 'w') as outfile:
    json.dump(exports, outfile, indent=2)

def get_lib_locations(f):
  """
  Reads a config file and returns a dictionary with categories as keys and
  lists of tuples as values, each containing
                          (software_type, contribution_name, download_url)
  """
  software_type = None
  category = None
  urls_by_category = {}
  for line in f.readlines():
    hash = line.find('#')
    line = line.strip() if hash == -1 else line[:hash]
    if len(line) == 0:
      continue

    if line[0] == '[' and line[-1] == ']':
      contents = line[1:-1]
      contents = contents.split(':')
      if len(contents) == 2:
        software_type = contents[0].strip()
        software_type = ''.join(software_type.split()).lower()
        category = contents[1].strip()
      else:
        software_type = None
        category = None
    else:
      if software_type == None or category == None:
        # XXX Error. Bad syntax for .conf file
        print('Ignoring contribution without type or category')
        continue

      contents = line.split('\\')
      if len(contents) != 2:
        print('Lines for contributions must be of the form "[Contribution ID] \ [Contribution URL]"')
        print(contents)
        continue

      name = contents[0].strip()
      url = contents[1].strip()

      if category not in urls_by_category:
        urls_by_category[category] = []
      urls_by_category[category].append((software_type, name, url))

  return urls_by_category

def missing_key(exports):
  keys = list(exports.keys())
  required_keys = ['name', 'authors', 'url', 'categories', 'sentence', 'version']
  for key in required_keys:
    if not keys.count(key):
      return key
  return None

if __name__ == "__main__":
  if len(argv) == 1:
    script = argv
    conf = 'sources.conf'
    dirout = '../sources/'
    minrev = 228
    maxrev = 0
  elif len(argv) == 3:
    script, conf, dirout = argv
    minrev = 228
    maxrev = 0
  elif len(argv) == 5:
    script, conf, dirout, minrev, maxrev = argv
  else:
    print("Usage is [Input File] [Output Dir] [Min Revision] [Max Revision]")
    exit()

  if (int(maxrev) != 0 and int(maxrev) < 228):
    print("Incompatible maxrev! This script is only for Processing 3.x. Please use build_listing_legacy.py instead.")
    exit()
  
  print("----- " + strftime("%a %d %b %Y %H:%M:%S", localtime()) + " -----")

  f = open(conf)
  urls_by_category = get_lib_locations(f)
  f.close()

  broken_ids = [line.rstrip('\n') for line in open('broken.conf')]
  skipped_ids = [line.rstrip('\n') for line in open('skipped.conf')]

  contribs_by_id = {}

  for cat in urls_by_category:
    contribs = urls_by_category[cat]

    for contrib in contribs:
      software_type, contrib_id, prop_url = contrib

      if (contrib_id in skipped_ids):
        print("Skipping " + contrib_id)
        continue

      download_url = prop_url[:prop_url.rfind('.')] + '.zip'
      try:
        print("Opening " + prop_url)
        exports = read_exports(urlopen(prop_url))

        exports['id'] = contrib_id
        exports['type'] = software_type

        exports['props'] = prop_url

        # overwrite the category with what was in the .conf file
        exports['categories'] = cat
        
        # set default compatible strings if none found
        if (not 'minRevision' in exports or exports['minRevision'] == ''):
          exports['minRevision'] = '0'
        # if (not 'maxRevision' in exports or exports['maxRevision'] == ''):
        #   if (contrib_id in broken_ids):
        #     exports['maxRevision'] = '228'
        #   else:
        #     exports['maxRevision'] = '0'
        if (contrib_id in broken_ids):
            exports['maxRevision'] = '228'
        else:
          if (not 'maxRevision' in exports or exports['maxRevision'] == ''):
            exports['maxRevision'] = '0'

        key = missing_key(exports)
        if key:
          print("Error reading " + prop_url)
          print("  No value for '%s'. Maybe it's a 404 page" % key)
          continue
        # if no download is explicitly provided, use the default download url
        m = re.compile('download.*')
        if len([x for x in exports if m.match(x)]) == 0:
          exports['download'] = download_url

        # add the contribution if it's compatible with the revision number
        if ((int(minrev) == 0 or int(exports['maxRevision']) == 0 or int(minrev) <= int(exports['maxRevision'])) and 
            (int(maxrev) == 0 or int(exports['minRevision']) == 0 or int(maxrev) >= int(exports['minRevision']))):
          if contrib_id not in contribs_by_id:
            # add the new contribution to the list
            contribs_by_id[contrib_id] = exports
          else:
            # append the category to the existing contribution
            contribs_by_id[contrib_id]['categories'] += "," + cat

      except IOError as inst:
        print("Error reading " + prop_url)
        print(inst)
        
      except UnicodeDecodeError as inst:
        print("Error decoding " + prop_url)
        print(inst)

  # create empty output dir
  if os.path.exists(dirout) and os.path.isdir(dirout):
    shutil.rmtree(dirout)
  if not os.path.exists(dirout):
    os.makedirs(dirout)

  # write all contributions out to files
  for contrib_id in contribs_by_id:
    contribs_by_id[contrib_id] = format_exports(contribs_by_id[contrib_id])
    write_exports(dirout, contribs_by_id[contrib_id])

