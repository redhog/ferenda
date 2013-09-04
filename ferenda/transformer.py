#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from tempfile import mkdtemp
import os
import shutil

import pkg_resources
from lxml import etree
from lxml.etree import XSLT

# assumption: A transformer is initialized with a single template. If
# you want to use a different template, create a different
# transformer.
class Transformer(object):
    def __init__(self, transformertype,
                       template,
                       templatedirs,
                       documentroot=None):
        cls = {'XSLT': XSLTTransform,
               'JINJA': JinjaTransform}[transformertype]
        self.t = cls(template, templatedirs)
        self.documentroot = documentroot

    # transform() always operate on the native datastructure -- this might 
    # be different depending on the transformer engine. For XSLT, which is 
    # implemented through lxml, its in- and outdata are lxml trees
    # 
    # If you want engine-indepent apis, use transform_stream or 
    # transform_file instead 
    #    
    # valid parameters 
    # - configurationfile: resources.xml -- cannot be calculated until
    #                                       we know the outfile
    # - annotationfile: intermediate/basefile.grit.xml
    def transform(self, indata, depth, parameters=None):
        if parameters == None:
            parameters = {}
        configfile = self.t.getconfig(depth)
        if configfile:
            parameters['configfile'] = configfile
        from pudb import set_trace; set_trace()
        outdata = self.t.transform(indata, parameters)
        return outdata

    # accepts a file-like object, returns a file-like object
    def transform_stream(self, instream,
                         parameters=None):
        return self.t.native_to_stream(
            self.transform(self.t.stream_to_native(instream),
                           
))
    # accepts two filenames, reads from one, writes to the other
    def transform_file(self, infile, outfile, parameters):
        depth = self._depth(outfile, self.documentroot)
        self.t.native_to_file(self.transform(self.t.file_to_native(infile),
                                             depth,
                                             parameters),
                              outfile)

    def _depth(self, outfile, root):
        # NB: root must be a dir, not a file
        return os.path.relpath(outfile, root).count("..")
        
class TransformerEngine(object):
    def __init__(self, template, templatedirs):
        pass

class XSLTTransform(TransformerEngine):
    def __init__(self, template, templatedirs):
        self.format = True # FIXME: make configurable
        self.templdir = self._setup_templates(template, templatedirs)
        worktemplate = self.templdir + os.sep + os.path.basename(template)
        assert os.path.exists(worktemplate)
        parser = etree.XMLParser(remove_blank_text=self.format)
        xsltree = etree.parse(worktemplate, parser)
        try:
            self._transformer = etree.XSLT(xsltree)
        except etree.XSLTParseError as e:
            raise errors.TransformError(str(e.error_log))


    # purpose: get all XSLT files (main and supporting) into one place
    #   (should support zipped eggs, even if setup.py don't)
    # template:     full path to actual template to be used 
    # templatedirs: directory of supporting XSLT templates
    # returns:      directory name of the place where all files ended up
    def _setup_templates(self, template, templatedirs):
        workdir = mkdtemp()
        # copy everything to this temp dir
        for d in templatedirs:
            if pkg_resources.resource_isdir('ferenda', d):
                for f in pkg_resources.resource_listdir('ferenda', d):
                    fp = pkg_resources.resource_stream('ferenda', d+"/"+f)
                    dest = workdir + os.sep + f
                    with open(dest, "wb") as dest_fp:
                        dest_fp.write(fp.read())
            elif os.path.exists(d) and os.path.isdir(d):
                for f in os.listdir(d):
                    shutil.copy2(d+os.sep+f, workdir+os.sep+f)
        if os.path.basename(template) not in os.listdir(workdir):
            shutil.copy2(template, workdir)
        return workdir

    # getconfig may return different data depending on engine -- in this case 
    # it creates a xml file and returns the path for it
    def getconfig(self, depth):
        pass

    # nativedata = lxml.etree
    def native_to_file(self, nativedata, outfile):
        res = self.html5_doctype_workaround(
            etree.tostring(nativedata, pretty_print=self.format))
        with open(outfile,"wb") as fp:
            fp.write(res)

    @staticmethod
    def html5_doctype_workaround(indata):
        # FIXME: This is horrible
        if indata.startswith(b"<remove-this-tag>"):
            indata = b"<!DOCTYPE html>\n"+indata[17:-18].strip()
            if indata[-1] == b"<" or indata[-1] == 60:
                indata = indata[:-1]
        return indata
            
    def file_to_native(self, infile):
        return etree.parse(infile)

    def transform(self, indata, parameters):
        strparams = {}
        for key, value in parameters.items():
            strparams[key] = XSLT.strparam(value)
        try:
            return self._transformer(indata,**parameters)
        except etree.XSLTApplyError as e:
            raise errors.TransformError(str(e.error_log))
        if len(transform.error_log) > 0:
            raise errors.TransformError(str(transform.error_log))
        # FIXME: hook in the transform_links step somehow?

class JinjaTransform(TransformerEngine):
    pass


# client code
# 
# doc.body = elements.Body()
# for r in res:
#     doc.body.append(html.Div(
#         [html.H2([elements.Link(r['title'], uri=r['uri'])]),
#          r['text']], **{'class':'hit'}))
# pages = [html.P(["Results %(firstresult)s-%(lastresult)s of %(totalresults)s" %          pager])]
# for pagenum in range(pager['pagecount']):
#     if pagenum + 1 == pager['pagenum']:
#         pages.append(html.Span([str(pagenum+1)],**{'class':'page'}))
#     else:
#         querystring['p'] = str(pagenum+1)
#         url = environ['PATH_INFO'] + "?" + urlencode(querystring)
#         pages.append(html.A([str(pagenum+1)],**{'class':'page',
#                                                 'href':url}))
# doc.body.append(html.Div(pages, **{'class':'pager'}))
# 
# transformer = TemplateTransformer(transformertype="XSLT",
#                                   template="res/xsl/generic.xsl",
#                                   templatedirs=["res/xsl"],
#                                   documentroot="/var/www/site")
# 
# newtree = transformer.transform_tree(doc.body.as_xhtml(),
#                                      reldepth=1)
# fp.write(etree.tostring(newtree, pretty_print=True))
# 
# # -- or --
#  
# 
# util.writefile("indata.xhtml", doc.body.as_xhtml().serialize())
# transformer.transform("indata.xhtml", "/var/www/site/my/own/file.html")
# 
# # references to root resources in file.html are now on the form 
# # "../../css/main.css", since file.html is 2 levels deep compared to 
# # documentroot. 
# 


