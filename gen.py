#!/usr/bin/python
'''The OpenGL bindings generator'''

__author__    = 'Alexandre Fournier'
__license__   = 'Boost Software License, Version 1.0'
__copyright__ = '2011, Alexandre Fournier <af at liquidstate.eu>'
__version__   = '0.1'

import os
import sys
import re

from lxml import etree, html
from datetime import datetime
from urllib import urlretrieve
from urlparse import urlparse

CACHE_PATH = 'cache'
GITHUB_URL = 'https://github.com/AlexandreFournier/gl-spec-parser'
GENERATION = '''
YOU DO NOT NEED TO EDIT THIS FILE DIRECTLY\n
It was automatically generated by %s on %s
Please contact the author or visit the project page for more information:\n
%s
''' % (sys.argv[0], str(datetime.now()), GITHUB_URL)

# 'base' and 'index' shoud be the same in 99% of cases,
# but it's faster to download .xml on http rather than webdav over https
URLS = {
	'gl2' : {
		'format' : 'docbook',
		'regexp' : r'^gl[A-Z][a-zA-Z0-9]*\.xml$',
		'xpath'  : '//file/@name',
		'index'  : 'https://cvs.khronos.org/svn/repos/ogl/trunk/ecosystem/public/sdk/docs/man/',
		'base'   : 'http://www.opengl.org/sdk/docs/man/',
		'list'   : [],
	},
	'gl3' : {
		'format' : 'docbook',
		'regexp' : r'^gl[A-Z][a-zA-Z0-9]*\.xml$',
		'xpath'  : '//file/@name',
		'index'  : 'https://cvs.khronos.org/svn/repos/ogl/trunk/ecosystem/public/sdk/docs/man3/',
		'base'   : 'http://www.opengl.org/sdk/docs/man3/',
		'list'   : [],
	},
	'gl4' : {
		'format' : 'docbook',
		'regexp' : r'^gl[A-Z][a-zA-Z0-9]*\.xml$',
		'xpath'  : '//file/@name',
		'index'  : 'https://cvs.khronos.org/svn/repos/ogl/trunk/ecosystem/public/sdk/docs/man4/',
		'base'   : 'http://www.opengl.org/sdk/docs/man4/',
		'list'   : [],
	},
	'glu' : {
		'format' : 'docbook',
		'regexp' : r'^glu[A-Z][a-zA-Z0-9]*\.xml$',
		'xpath'  : '//file/@name',
		'index'  : 'https://cvs.khronos.org/svn/repos/ogl/trunk/ecosystem/public/sdk/docs/man/',
		'base'   : 'http://www.opengl.org/sdk/docs/man/',
		'list'   : [],
	},
	'glX' : {
		'format' : 'docbook',
		'regexp' : r'^glX[A-Z][a-zA-Z0-9]*\.xml$',
		'xpath'  : '//file/@name',
		'index'  : 'https://cvs.khronos.org/svn/repos/ogl/trunk/ecosystem/public/sdk/docs/man/',
		'base'   : 'http://www.opengl.org/sdk/docs/man/',
		'list'   : [],
	},
	'glext' : {
		'format' : 'extspec',
		'regexp' : r'^specs/[A-Z]+/[a-zA-Z0-9_]+\.txt$',
		'xpath'  : '//a/@href',
		'index'  : 'http://www.opengl.org/registry/',
		'base'   : 'http://www.opengl.org/registry/',
		'list'   : [],
	},
	'glenums' : {
		'format' : 'dotspec',
		'regexp' : r'^api/[a-z]*enum(?:ext)?\.spec$',
		'xpath'  : '//a/@href',
		'index'  : 'http://www.opengl.org/registry/',
		'base'   : 'http://www.opengl.org/registry/',
	},
	'glfuncs' : { # we don't really care about those
		'format' : 'dotspec',
		'regexp' : r'^api/w?glx?(?:ext)?\.spec$',
		'xpath'  : '//a/@href',
		'index'  : 'http://www.opengl.org/registry/',
		'base'   : 'http://www.opengl.org/registry/',
	},
	'gltypes' : { # we don't really care about those
		'format' : 'dottm',
		'regexp' : r'^api/[a-z]+\.tm$',
		'xpath'  : '//a/@href',
		'index'  : 'http://www.opengl.org/registry/',
		'base'   : 'http://www.opengl.org/registry/',
	},
}

# At least this is less ugly than Khronos specifications
FIXES = {
	# This function prototype will never be parsed
	'http://www.opengl.org/registry/specs/SGIS/texture_color_mask.txt' : lambda x : x.replace(
		'void TextureColorMaskSGIS(boolean r, boolean g, boolean, b, boolean a );',
		'void TextureColorMaskSGIS(boolean r, boolean g, boolean b, boolean a );'
	),
	# This makes the parsing more difficult
	'http://www.opengl.org/registry/specs/IBM/multimode_draw_arrays.txt' : lambda x : x.replace(
		'sizeof(GLenum)',
		'size of GLenum'
	),
	# This makes the parsing more difficult
	'http://www.opengl.org/registry/specs/SGIX/instruments.txt' : lambda x : x.replace(
		'    An example of using the calls to test the extension:',
		'Misc\n    An example of using the calls to test the extension:'
	),
	# This makes the parsing more difficult, they also put typedef struct in "New Procedures and Functions"
	'http://www.opengl.org/registry/specs/SGIX/hyperpipe_group.txt' : lambda x : x.replace(
		'(pixels)',
		'in pixels'
	),
	# Someone forgot to put a name on the last parameter
	'http://www.opengl.org/registry/specs/MESA/window_pos.txt' : lambda x : x.replace(
		'void WindowPos4dMESA(double x, double y, double z, double )',
		'void WindowPos4dMESA(double x, double y, double z, double w)'
	),
	# This makes the parsing more difficult
	'http://www.opengl.org/registry/specs/ARB/get_proc_address.txt' : lambda x : x.replace(
		'void (*glXGetProcAddressARB(const GLubyte *procName))(...)',
		'GLfunction glXGetProcAddressARB(const GLubyte *procName)'
	),
	# This one use undefined templated function declarations
	'http://www.opengl.org/registry/specs/OES/OES_fixed_point.txt' : lambda x : '',
}

# Caching should be done in urllib
class Resolver(etree.Resolver):
	'''A DTD resolver with caching'''
	@staticmethod
	def cache(system_url):
		url = urlparse(system_url)
		if url.scheme == '':
			if url.path.startswith(CACHE_PATH):
				system_url = system_url.replace(CACHE_PATH, 'http:/') # not safe
				url = urlparse(system_url)
		if url.scheme == 'http' or url.scheme == 'https':
			urlPath, urlFile = os.path.split(url.path)
			urlPath = urlPath.replace("/", os.sep)
			urlPath = url.hostname + urlPath
			locPath = os.path.join(CACHE_PATH, urlPath) 
			locFile = os.path.join(locPath, urlFile)
			if not os.path.exists(locPath):
				os.makedirs(locPath)
			if locFile.endswith(os.sep):
				locFile += 'INDEX'
			if not os.path.exists(locFile):
				print 'retrieving %s' % system_url
				urlretrieve(system_url, locFile)
				if system_url in FIXES:
					print 'fixing %s' % system_url
					fixed = FIXES[system_url](open(locFile).read())
					open(locFile, 'w').write(fixed);
			return locFile
		return None

	def resolve(self, system_url, system_id, context):
		file = Resolver.cache(system_url)
		if not file == None:
			return self.resolve_filename(file, context)

# Registering the Resolver as the default DTD resolver
parser = etree.XMLParser(load_dtd=True)
parser.resolvers.add(Resolver())
etree.set_default_parser(parser)

# Loading file lists from index pages
for key in URLS.keys():
	file = Resolver.cache(URLS[key]['index'])
	root = html.parse(file)
	uris = root.xpath(URLS[key]['xpath'])
	URLS[key]['list'] = filter(lambda x : re.match(URLS[key]['regexp'], x), uris)
	URLS[key]['list'].sort()

# An ugly XLST stylesheet to render the documentation
XSLT_params = etree.XSLT(etree.XML('''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
	<xsl:template match="variablelist">
		<root><xsl:apply-templates/></root>
	</xsl:template>

	<xsl:variable name='space'><xsl:text> </xsl:text></xsl:variable>
	<xsl:variable name='newline'><xsl:text>
</xsl:text></xsl:variable>

	<xsl:template match="text()">
		<xsl:if test="normalize-space(.)">
			<xsl:value-of select="normalize-space(.)"/>
			<xsl:value-of select="$space" />
		</xsl:if>
	</xsl:template>

	<xsl:template match="para">
		<xsl:apply-templates/>
		<xsl:value-of select="$newline" />
		<xsl:value-of select="$newline" />
	</xsl:template>
</xsl:stylesheet>
'''))

class ReferenceParser:
	'''A class to parse Khronos OpenGL docbook man pages'''

	def __init__(self, name):
		self.functions = None

	def parse_file(self, file):
		dom = etree.parse(file)
		lst = FunctionList()
		# decode functions prototypes
		lst = FunctionList()
		funcdef = dom.xpath('/refentry/refsynopsisdiv/funcsynopsis/funcprototype')
		for elem in funcdef:
			type = elem.xpath('funcdef')[0].text.strip()
			name = elem.xpath('funcdef')[0].getchildren()[0].text.strip()
			dfunction = Function(name, type)
			paramdef = elem.xpath('paramdef')
			for elem in paramdef:
				if elem.text == None:
					break
				type = elem.text.strip()
				name = elem.xpath('parameter')
				if len(name) > 0:
					name = name[0].text.strip()
					dfunction.addParameter(type, name)
			lst.append(dfunction)
		# decode functions documentation
		ref1 = dom.xpath('/refentry/refnamediv/refname')[0].text.strip()
		ref2 = dom.xpath('/refentry/refnamediv/refpurpose')[0].text.strip()
		ddoc = '%s - %s\n\n' % (ref1, ref2)
		lst.addDocumentation(ddoc)
		variablelist = dom.xpath('/refentry/refsect1[@id="parameters"]/variablelist')
		if False and len(variablelist) > 0: # FIXME
			variablelist = variablelist[0]
			node = XSLT_params(variablelist)
			ddoc = unicode(node.getroot().text)
			lst.addDocumentation(ddoc)
		self.functions = lst

class EnumerantParser:
	'''A class to parse Khronos OpenGL .spec'''

	def __init__(self):
		self.enumerants = EnumerantList()
	
	def parse_file(self, file):
		file = Resolver.cache(file)
		lines = open(file, 'r').read().splitlines()

		prefix = 'GL_'
		if 'glx' in file:
			prefix = 'GLX_'
		if 'wgl' in file:
			prefix = 'WGL_'

		enums = {}
		for line in lines:
			pos = line.find('#')
			if pos != -1:
				line = line[0:pos]
			line = line.strip()
			if len(line) == 0:
				continue
			m = re.match('^([a-zA-Z0-9_]+)\s*=\s*([a-zA-Z0-9_]+)', line)
			if m:
				name = m.group(1)
				data = m.group(2)
				if not name.startswith(prefix):
					name = prefix + name
				enums[name] = data
		for key,enum in enums.items():
			if enum in enums.keys():
				enums[key] = enums[enum]
		for key,enum in enums.items():
			self.enumerants.append(Enumerant(key, enum))
			

class ExtensionParser:
	'''A class to parse Khronos extensions specifications,
	most of the regular expressions and code logic comes from Glew 
	git://glew.git.sourceforge.net/glew/glew/auto/bin/parse_spec.pl'''

	re = {
		'name'     : re.compile(r'^([a-z0-9]+)_([a-z0-9_]+)', flags=re.IGNORECASE),
		'AtoZ'     : re.compile(r'^[A-Z]'),
		'eofunc'   : re.compile(r'.*(?:\);?$|^$)'),
		'extname'  : re.compile(r'^[A-Z][A-Za-z0-9_]+$'),
		'none'     : re.compile(r'^\(none\)$'),
		'function' : re.compile(r'^(.+) ([a-z][a-z0-9_]*) \((.+)\)$', flags = re.IGNORECASE),
		'prefix'   : re.compile(r'^(?:[aw]?gl|glX)'),
		'tprefix'  : re.compile(r'^(?:[AW]?GL|GLX)_'),
		'token'    : re.compile(r'^([A-Z0-9][A-Z0-9_x]*):?\s+((?:0x)?[0-9A-F]+)(.*)$'),
	}

	def __init__(self):
		self.extension = None

	@staticmethod
	def clean_function(str):
		str = re.sub(r' +', ' ', str)
		str = re.sub(r'<.*>', '',  str)
		str = re.sub(r'<.*', '',  str)
		str = re.sub(r'\s*\(\s*', ' (',  str)
		str = re.sub(r'\s*\)\s*', ')', str)
		str = re.sub(r'\s*\*([a-zA-Z])', '* \\1', str)
		str = re.sub(r'\*wgl', '* wgl', str)
		str = re.sub(r'\*glX', '* glX', str)
		str = re.sub(r'\.\.\.', 'void', str)
		str = re.sub(r'\.\.\.', 'void', str)
		str = re.sub(r';$', '', str)
		return str

	def parse_file(self, file):
		file = Resolver.cache(file)
		lines = open(file, 'r').read().splitlines()
		section = None
		for line in lines:
			line = line.rstrip()
			if re.match(self.re['AtoZ'], line):
				section = line
			elif section:
				line = line.lstrip()
				self.parse_line(line, section)

	_func = ""
	def parse_line(self, line, section):
		if section == 'Name':
			m = re.match(self.re['name'], line)
			if not m:
				return
			name = "%s_%s" % (m.group(1), m.group(2))
			self.extension = Extension(name)
		if section == 'Name String' or section == 'Name Strings':
			m = re.match(self.re['name'], line)
			if m:
				self.extension.append(self.extension.name)
			m = re.match(self.re['extname'], line)
			if m:
				name = m.group(0)
				m = re.match(self.re['tprefix'], line)
				if not m:
					name = "GL_" + name
				self.extension.append(name)
		if section == 'New Procedures and Functions':
			m = re.match(self.re['eofunc'], line)
			if m:
				self._func += ' %s' % line
				self._func = ExtensionParser.clean_function(self._func)
				m = re.match(self.re['function'], self._func)
				if m:
					type     = self.resolve_type(m.group(1).strip())
					name     = m.group(2)
					function = Function(name, type)
					params = m.group(3)
					for param in map(lambda x: x.strip().split(), params.split(',')):
						if len(param) == 1 and param[0].lower() == 'void':
							continue
						type = self.resolve_type(' '.join(param[0:-1]))
						name = param[-1]
						function.addParameter(type, name)
					self.extension.append(function)
				self._func = ""
			else:
				self._func += ' %s' % line
		if section == 'New Tokens':
			m = re.match(self.re['token'], line)
			if m:
				name  = m.group(1)
				value = m.group(2)
				if not name.startswith('GL_'):
					name = 'GL_' + name
				self.extension.append(Const(name, value))
	
	def resolve_type(self, type):
		types = {
			'fixed'                   : 'GLfixed',
			'function'                : 'GLfunction',
			'void'                    : 'GLvoid',
			'VOID'                    : 'GLvoid',
			'boolean'                 : 'GLboolean',
			'Boolean'                 : 'GLboolean',
			'Bool'                    : 'GLboolean',
			'BOOL'                    : 'GLboolean',
			'Boolean'                 : 'GLboolean',
			'bitfield'                : 'GLbitfield',
			'enum'                    : 'GLenum',
			'byte'                    : 'GLbyte',
			'char'                    : 'GLchar',
			'charARB'                 : 'GLchar',
			'ubyte'                   : 'GLubyte',
			'short'                   : 'GLshort',
			'ushort'                  : 'GLushort',
			'int'                     : 'GLint',
			'unsignedint'             : 'GLuint',
			'UINT'                    : 'GLuint',
			'uint'                    : 'GLuint',
			'uint'                    : 'GLuint',
			'half'                    : 'GLhalf',
			'long'                    : 'GLlong',
			'unsignedlong'            : 'GLulong',
			'float'                   : 'GLfloat',
			'FLOAT'                   : 'GLfloat',
			'double'                  : 'GLdouble',
			'clampf'                  : 'GLclampf',
			'clampd'                  : 'GLclampd',
			'INT'                     : 'GLint',
			'INT32'                   : 'GLint32',
			'int32_t'                 : 'GLint32',
			'int64EXT'                : 'GLint64',
			'int64'                   : 'GLint64',
			'INT64'                   : 'GLint64',
			'int64_t'                 : 'GLint64',
			'uint64EXT'               : 'GLuint64',
			'int64EXT'                : 'GLint64',
			'uint64'                  : 'GLuint64',
			'uint64EXT'               : 'GLuint64',
			'sizeiptr'                : 'GLsizeiptr',
			'intptr'                  : 'GLintptr',
			'intptrARB'               : 'GLintptr',
			'sizei'                   : 'GLsizei',
			'sizeiptrARB'             : 'GLsizeiptr',
			'handleARB'               : 'GLhandle',
			'sync'                    : 'GLsync',
			'vdpauSurfaceNV'          : 'GLvdpauSurfaceNV',
			'XContext'                : 'GLXContext',
			'XDrawable'               : 'GLXDrawable',
			'XPixmap'                 : 'GLXPixmap',
			'XVideoSourceSGIX'        : 'GLXVideoSourceSGIX',
			'XVideoCaptureDeviceNV'   : 'GLXVideoCaptureDeviceNV',
			'XVideoDeviceNV'          : 'GLXVideoDeviceNV',
			'XFBConfigID'             : 'XID',
			'XContextID'              : 'XID',
			'XWindow'                 : 'XID',
			'XPbuffer'                : 'XID',
			'XFBConfigIDSGIX'         : 'XID',
			'XFBConfigSGIX'           : 'void*',
			'XFBConfig'               : 'void*',
			'DEBUGPROCAMD'            : 'GLDEBUGPROCAMD',
			'DEBUGPROCARB'            : 'GLDEBUGPROCARB',
			'DMbuffer'                : 'void*',
			'Display'                 : 'Display',
			'Window'                  : 'Window',
			'Pixmap'                  : 'Pixmap',
			'Status'                  : 'Status',
			'Colormap'                : 'Colormap',
			'XVisualInfo'             : 'XVisualInfo',
			'HDC'                     : 'HDC',
			'HANDLE'                  : 'HANDLE',
			'HGLRC'                   : 'HGLRC',
			'HPBUFFERARB'             : 'HPBUFFERARB',
			'HPBUFFEREXT'             : 'HPBUFFEREXT',
			'VLNode'                  : 'VLNode',
			'VLPath'                  : 'VLPath',
			'VLServer'                : 'VLServer',
			'handleARB'               : 'handleARB',
			'HVIDEOOUTPUTDEVICENV'    : 'HVIDEOOUTPUTDEVICENV',
			'HVIDEOINPUTDEVICENV'     : 'HVIDEOINPUTDEVICENV',
			'HPVIDEODEV'              : 'HPVIDEODEV',
			'cl_context'              : 'cl_context',
			'cl_event'                : 'cl_event',
			'XPbufferSGIX'            : 'GLXPbufferSGIX',
			'XHyperpipeNetworkSGIX'   : 'GLXHyperpipeNetworkSGIX',
			'XHyperpipeConfigSGIX'    : 'GLXHyperpipeConfigSGIX',
			'DMparams'                : 'DMparams',
		}
		ptrs = type.count('*')
		type = type.replace('*', '')
		type = type.replace(' ', '')
		type = type.replace('const', '')
		if type.startswith('GL') or type.startswith('Gl'):
			type = type[2:]
		if not type in types:
			raise Exception('type not found : %s' % type)
		return types[type] + '*' * ptrs

class Module:
	'''Abstraction class for a module (D module, C header, SWIG specification, etc.)'''

	def __init__(self, name):
		self.name       = name
		self.libraries  = LibraryList()
		self.extensions = None
		self.enumerants = None

	def digest(self, name):
		if URLS[name]['format'] == 'docbook':
			library = Library(name)
			for file in URLS[name]['list']:
				file = '%s%s' % (URLS[name]['base'], file)
				print >> sys.stderr, 'parsing %s' % file
				parser = ReferenceParser(name)
				parser.parse_file(file)
				library.append(parser.functions)
			self.libraries.append(library)

		if URLS[name]['format'] == 'extspec':
			self.extensions = ExtensionList()
			for file in URLS[name]['list']:
				file = '%s%s' % (URLS[name]['base'], file)
				print >> sys.stderr, 'parsing %s' % file
				parser = ExtensionParser()
				parser.parse_file(file)
				if parser.extension != None:
					self.extensions.append(parser.extension)

		if URLS[name]['format'] == 'dotspec':
			self.enumerants = EnumerantList()
			for file in URLS[name]['list']:
				file = '%s%s' % (URLS[name]['base'], file)
				print >> sys.stderr, 'parsing %s' % file
				parser = EnumerantParser()
				parser.parse_file(file)
				self.enumerants += parser.enumerants

	def append(self, object):
		if isinstance(object, FunctionList):
			self.functionlists.append(object)

	def toD(self, writer):
 		writer.writeln()
		writer.writeln('module %s;' % self.name)
		writer.writeln()
		for alias in [
			Alias('GLenum',     'uint'),
			Alias('GLboolean',  'ubyte'),
			Alias('GLbitfield', 'uint'),
			Alias('GLvoid',     'void'),
			Alias('GLbyte',     'byte'),
			Alias('GLshort',    'short'),
			Alias('GLint',      'int'),
			Alias('GLubyte',    'ubyte'),
			Alias('GLushort',   'ushort'),
			Alias('GLuint',     'uint'),
			Alias('GLsizei',    'int'),
			Alias('GLfloat',    'float'),
			Alias('GLclampf',   'float'),
			Alias('GLdouble',   'double'),
			Alias('GLclampd',   'double'),
			Alias('GLchar',     'char'),
			Alias('GLintptr',   'ptrdiff_t'),
			Alias('GLsizeptr',  'ptrdiff_t')]:
			alias.toD(writer)
		if self.libraries:
			writer.writeln()
			writer.writeln('extern(C)')
			writer.writeln('{')
			writer.indent()
			for i, library in enumerate(self.libraries):
				if i > 0:
					writer.writeln()
					writer.writeln()
				library.toD(writer)
			writer.deindent()
			writer.writeln('}')
		if self.extensions:
			writer.writeln()
			for i, extension in enumerate(self.extensions):
				if i > 0:
					writer.writeln()
				extension.toD(writer)

	def toXML(self):
		node = etree.Element('module', name = self.name)
		node.append(etree.Comment(GENERATION))
		if self.enumerants:
			node.append(self.enumerants.toXML())
		if self.libraries:
			node.append(self.libraries.toXML())
		if self.extensions:
			node.append(self.extensions.toXML())
		return node

class Documentation(list):
	'''Abstraction class for documentation string'''

	def toXML(self):
		node = etree.Element('documentation')
		node.text = '\n'.join(self)
		return node

class LibraryList(list):

	def toXML(self):
		node = etree.Element('libraries')
		if len(self) == 0:
			return node
		for item in self:
			node.append(item.toXML())
		return node
		
class Library(list):

	def __init__(self, name):
		self.name = name

	def toXML(self):
		node = etree.Element('library', name = self.name)
		if len(self) == 0:
			return node
		for item in self:
			node.append(item.toXML())
		return node
	
	def toD(self, writer):
		if len(self) == 0:
			return
		for item in self:
			item.toD(writer)

class ExtensionList(list):

	def toXML(self):
		node = etree.Element('extensions')
		for extension in self:
			node.append(extension.toXML())
		return node

class Extension:
	'''Abstration for OpenGL extension'''

	def __init__(self, name):
		self.name      = name
		self.consts    = ConstList()
		self.functions = FunctionList()
	
	def append(self, object):
		if isinstance(object, Const):
			self.consts.append(object)
		if isinstance(object, Function):
			self.functions.append(object)
	
	def toD(self, writer):
		writer.writeln("struct %s" % self.name)
		writer.writeln("{")
		writer.indent()
		for const in self.consts:
			const.toD(writer)
		if len(self.consts) > 0 and len(self.functions) > 0:
			writer.writeln()
		for function in self.functions:
			function.toD(writer)
		writer.deindent()
		writer.writeln("}")

	def toXML(self):
		node = etree.Element('extension', name = self.name)
		node.append(self.consts.toXML())
		node.append(self.functions.toXML())
		return node

class ConstList(list):

	def toXML(self):
		node = etree.Element('consts')
		for item in self:
			node.append(item.toXML())
		return node

class Const:
	'''Abstraction class for D const'''

	def __init__(self, name, value, type = None):
		self.name  = name
		self.value = value
		self.type  = type
	
	def toD(self, writer):
		writer.write("const ")
		if self.type:
			writer.write("%s " % self.type)
		writer.writeln("%s = %s;" % (self.name, self.value))

	def toXML(self):
		if self.type == None:
			return etree.Element('const',
				name  = self.name,
				value = self.value)
		else:
			return etree.Element('const',
				name  = self.name,
				value = self.value,
				type  = self.type)

EnumerantList = ConstList
Enumerant = Const

class AliasList(list):
	'''Abstraction class for a list of D alias'''

	def toXML(self):
		node = etree.Element("aliases")
		for alias in self:
			node.append(alias.toXML())
		return node

class Alias:
	'''Abstration for D alias'''

	def __init__(self, name, type):
		self.name = name
		self.type = type

	def toD(self, writer):
		writer.writeln('alias %s %s;' % (self.type, self.name))

	def toXML(self):
		return etree.Element('alias',
			name = self.name,
			type = self.type)

class FunctionList(list):
	'''Abstraction class for a list of D functions'''

	def __init__(self):
		self.documentation = Documentation()

	def addDocumentation(self, documentation):
		self.documentation += documentation.splitlines()

	def toD(self, writer):
		writer.writeln('/**')
		for line in self.documentation:
			writer.writeln(' * %s' % line)
		writer.writeln(' */')
		for (i,function) in enumerate(self):
			if i > 0:
				writer.writeln('/// ditto')
			function.toD(writer)

	def toXML(self):
		node = etree.Element("functions")
		if len(self.documentation) > 0:
			node.append(self.documentation.toXML())
		for function in self:
			node.append(function.toXML())
		return node

class Function:
	'''Abstraction class for a D function'''

	def __init__(self, name, type = "void"):
		self.name = name
		self.type = self.typeC2D(type)
		self.params = []

	def addParameter(self, type, name):
		type = self.typeC2D(type)
		name = self.nameC2D(name)
		self.params.append({'type' : type, 'name' : name})

	def nameC2D(self, name):
		if name == 'ref':
			name = '_ref'
		return name

	def typeC2D(self, type):
		if type.startswith('const '):
			type = type[6:]
		if type.startswith('unsigned '):
			type = 'u' + type[9:]
		if type == 'void(*)()':
			type = 'void function()'
		return type

	def toD(self, writer):
		params = map(lambda x: '%s %s' % (x['type'], x['name']), self.params)
		params = ', '.join(params)
		writer.writeln('%s %s(%s);' % (self.type, self.name, params))

	def toXML(self):
		node = etree.Element('function',
			type = self.type,
			name = self.name)
		for param in self.params:
			etree.SubElement(node, 'param',
				type = param['type'],
				name = param['name'])
		return node

class Writer:
	'''A very stupid file writer for indentation'''
	def __init__(self, filename):
		self._indent = 0
		self.buffer = ""
		print >> sys.stderr, 'opening %s' % filename
		self.file  = open(filename, 'w')
	def __del__(self):
		print >> sys.stderr, 'done'
		self.file.close()
	def indent(self):
		self._indent += 1
	def deindent(self):
		self._indent -= 1
	def write(self, *args):
		for arg in args:
			self.buffer += arg
	def writeln(self, *args):
		self.file.write('\t' * self._indent)
		self.file.write(self.buffer)
		for arg in args:
			self.file.write(*args)
		self.file.write('\n')
		self.buffer = ""

if __name__ == '__main__':

	from optparse import OptionParser
	parser = OptionParser(usage="usage: %prog [options] <module> <gl.xml|gl.d>")
	parser.add_option('--all',     action='store_true', dest='all',     help='All')
	parser.add_option('--glenums', action='store_true', dest='glenums', help='OpenGL enums')
	parser.add_option('--gl2',     action='store_true', dest='gl2',     help='OpenGL 2')
	parser.add_option('--gl3',     action='store_true', dest='gl3',     help='OpenGL 3')
	parser.add_option('--gl4',     action='store_true', dest='gl4',     help='OpenGL 4')
	parser.add_option('--glu',     action='store_true', dest='glu',     help='GLU')
	parser.add_option('--glX',     action='store_true', dest='glX',     help='GLX')
	parser.add_option('--glext',   action='store_true', dest='glext',   help='OpenGL extensions')
	(options, args) = parser.parse_args()

	if len(args) != 1:
		parser.print_help()
		sys.exit(1)

	ext = os.path.splitext(args[0])[-1]
	if not ext in ['.d', '.xml']:
		print "Unknown extension try .xml or .d"
		sys.exit(1)

	module = Module('gl')

	if options.all or options.glenums:
		module.digest('glenums')

	if options.all or options.gl2:
		module.digest('gl2')

	if options.all or options.gl3:
		module.digest('gl3')

	if options.all or options.gl4:
		module.digest('gl4')

	if options.all or options.glu:
		module.digest('glu')

	if options.all or options.glX:
		module.digest('glX')
	
	if options.all or options.glext:
		module.digest('glext')

	if ext == '.d':
		module.toD(Writer(args[0]))
		sys.exit(0)

	if ext == '.xml':
		root = module.toXML()
		data = etree.tostring(root, pretty_print=True)
		open(args[0], "w").write(data)
		sys.exit(0)

sys.exit(2)



