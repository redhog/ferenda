# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os, sys
from ferenda.compat import unittest, Mock, patch

from ferenda import manager
manager.setup_logger('CRITICAL')

if os.getcwd() not in sys.path: sys.path.insert(0,os.getcwd())

from io import BytesIO
import codecs
import json
import shutil

from lxml import etree
from rdflib import Graph, Namespace
from rdflib.namespace import RDF, DC
from rdflib.namespace import DCTERMS as DCT
SCHEMA = Namespace("http://schema.org/")

from ferenda import DocumentRepository, Facet
from ferenda import manager, util, fulltextindex
from ferenda.elements import html
from ferenda.testutil import RepoTester

# tests the wsgi app in-process, ie not with actual HTTP requests, but
# simulates what make_server().serve_forever() would send and
# recieve. Should be simple enough, yet reasonably realistic, for
# testing the API.
class WSGI(RepoTester): # base class w/o tests
    def setUp(self):
        super(WSGI,self).setUp()
        self.app = manager.make_wsgi_app(port=8000,
                                         documentroot=self.datadir,
                                         apiendpoint="/myapi/",
                                         searchendpoint="/mysearch/",
                                         url="http://localhost:8000/",
                                         repos = [self.repo])
        self.env = {'HTTP_ACCEPT': 'text/xml, application/xml, application/xhtml+xml, text/html;q=0.9, text/plain;q=0.8, image/png,*/*;q=0.5',
                    'PATH_INFO':   '/',
                    'SERVER_NAME': 'localhost',
                    'SERVER_PORT': '8000',
                    'QUERY_STRING': '',
                    'wsgi.url_scheme': 'http'}

        self.put_files_in_place()

    def ttl_to_rdf_xml(self, inpath, outpath):
        g = Graph()
        g.parse(source=open(inpath), format="turtle")
        with self.repo.store._open(outpath, "wb") as fp:
            fp.write(g.serialize(format="pretty-xml"))
        return g

    def put_files_in_place(self):
        # Put files in place: parsed
        util.ensure_dir(self.repo.store.parsed_path("123/a"))
        shutil.copy2("test/files/base/parsed/123/a.xhtml",
                     self.repo.store.parsed_path("123/a"))

        g = self.ttl_to_rdf_xml("test/files/base/distilled/123/a.ttl",
                                self.repo.store.distilled_path("123/a"))

        # generated
        util.ensure_dir(self.repo.store.generated_path("123/a"))
        shutil.copy2("test/files/base/generated/123/a.html",
                     self.repo.store.generated_path("123/a"))

        # annotations
        util.ensure_dir(self.repo.store.annotation_path("123/a"))
        shutil.copy2("test/files/base/annotations/123/a.grit.xml",
                     self.repo.store.annotation_path("123/a"))

        # config
        resources = self.datadir+os.sep+"rsrc"+os.sep+"resources.xml"
        util.ensure_dir(resources)
        shutil.copy2("test/files/base/rsrc/resources.xml",
                     resources)

        # index.html
        index = self.datadir+os.sep+"index.html"
        with open(index, "wb") as fp:
            fp.write(b'<h1>index.html</h1>')

        # toc/index.html + toc/title/a.html
        with self.repo.store.open("index", "toc", ".html", "wb") as fp:
            fp.write(b'<h1>TOC for base</h1>')
        with self.repo.store.open("title/a", "toc", ".html", "wb") as fp:
            fp.write(b'<h1>Title starting with "a"</h1>')

        # distilled/dump.nt
        with self.repo.store.open("dump", "distilled", ".nt", "wb") as fp:
            fp.write(g.serialize(format="nt"))
        

    def call_wsgi(self, environ):
        start_response = Mock()
        buf = BytesIO()
        for chunk in self.app(environ, start_response):
            buf.write(chunk)
        call_args = start_response.mock_calls[0][1]
        # call_kwargs = start_response.mock_calls[0][2]
        return call_args[0], call_args[1], buf.getvalue()


    def assertResponse(self,
                       wanted_status,
                       wanted_headers,
                       wanted_content,
                       got_status,
                       got_headers,
                       got_content):
        self.assertEqual(wanted_status, got_status)
        got_headers = dict(got_headers)
        for (key, value) in wanted_headers.items():
            self.assertEqual(got_headers[key], value)
        if wanted_content:
            self.assertEqual(wanted_content, got_content)

class Fileserving(WSGI):
    def test_index_html(self):
        self.env['PATH_INFO'] = '/'
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'text/html'},
                            b'<h1>index.html</h1>',
                            status, headers, content)

    def test_not_found(self):
        self.env['PATH_INFO'] = '/nonexistent'
        status, headers, content = self.call_wsgi(self.env)
        msg = '<h1>404</h1>The path /nonexistent not found at %s/nonexistent' % self.datadir
        self.assertResponse("404 Not Found",
                            {'Content-Type': 'text/html'},
                            msg.encode(),
                            status, headers, content)
    
class API(WSGI):
    def setUp(self):
       super(API, self).setUp()
       self.env['PATH_INFO'] = '/myapi/'

    def test_basic(self):
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'application/json'},
                            None,
                            status, headers, content)
        got = json.loads(content.decode())
        want = {'current': '/myapi/?',
                  'duration': None,
                  'items': [],
                  'itemsPerPage': 10,
                  'startIndex': -10, # Hmm, probably not correct
                  'totalResults': 0}
        self.assertEqual(want, got)
        
class Runserver(WSGI):
    def test_make_wsgi_app_args(self):
        res = manager.make_wsgi_app(port='8080',
                                    documentroot=self.datadir,
                                    apiendpoint='/api-endpoint/',
                                    searchendpoint='/search-endpoint/',
                                    repos=[])
        self.assertTrue(callable(res))

    def test_make_wsgi_app_ini(self):
        inifile = self.datadir + os.sep + "ferenda.ini"
        with open(inifile, "w") as fp:
            fp.write("""[__root__]
datadir = /dev/null
url = http://localhost:7777/
apiendpoint = /myapi/
searchendpoint = /mysearch/            
""")
        res = manager.make_wsgi_app(inifile)
        self.assertTrue(callable(res))
    
    def test_runserver(self):
        m = Mock()
        with patch('ferenda.manager.make_server', return_value=m) as m2:
            manager.runserver([])
            self.assertTrue(m2.called)
            self.assertTrue(m.serve_forever.called)

class ConNeg(WSGI):
    def setUp(self):
       super(ConNeg, self).setUp()
       self.env['PATH_INFO'] = '/res/base/123/a'

    def test_basic(self):
        # basic test 1: accept: text/html -> generated file
        # Note that our Accept header has a more complicated value 
        # typical of a real-life browse
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'text/html'},
                            util.readfile(self.repo.store.generated_path("123/a"), "rb"),
                            status, headers, content)

    def test_xhtml(self):
        # basic test 2: accept: application/xhtml+xml -> parsed file
        self.env['HTTP_ACCEPT'] = 'application/xhtml+xml'
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'application/xhtml+xml'},
                            util.readfile(self.repo.store.parsed_path("123/a"), "rb"),
                            status, headers, content)

    def test_rdf(self):
        # basic test 3: accept: application/rdf+xml -> RDF statements (in XML)
        self.env['HTTP_ACCEPT'] = 'application/rdf+xml'
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'application/rdf+xml'},
                            util.readfile(self.repo.store.distilled_path("123/a"), "rb"),
                            status, headers, content)

    def test_ntriples(self):
        # Serialization may upset order of triples -- it's not
        # guaranteed that two isomorphic graphs serialize to the exact
        # same byte stream. Therefore, we only compare headers, not
        # content, and follow up with a proper graph comparison
        
        # transform test 4: accept: text/plain -> RDF statements (in NTriples)
        g = Graph()
        g.parse(source=self.repo.store.distilled_path("123/a"))
        self.env['HTTP_ACCEPT'] = 'text/plain'
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'text/plain'},
                            None,
                            status, headers, None)
        got = Graph()
        got.parse(data=content, format="nt")
        self.assertEqualGraphs(g, got)

    def test_turtle(self):
        # transform test 5: accept: text/turtle -> RDF statements (in Turtle)
        g = Graph()
        g.parse(source=self.repo.store.distilled_path("123/a"))
        self.env['HTTP_ACCEPT'] = 'text/turtle'
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'text/turtle'},
                            None,
                            status, headers, None)
        got = Graph()
        got.parse(data=content, format="turtle")
        self.assertEqualGraphs(g, got)
        
    def test_unacceptable(self):
        self.env['HTTP_ACCEPT'] = 'application/pdf'
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("406 Not Acceptable",
                            {'Content-Type': 'text/html'},
                            None,
                            status, headers, None)
    
    def test_extended_rdf(self):
        # extended test 6: accept: "/data" -> extended RDF statements
        self.env['PATH_INFO'] = self.env['PATH_INFO'] + "/data"
        self.env['HTTP_ACCEPT'] = 'application/rdf+xml'
        g = Graph()
        g.parse(source=self.repo.store.distilled_path("123/a"))
        g += self.repo.annotation_file_to_graph(self.repo.store.annotation_path("123/a"))
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'application/rdf+xml'},
                            None,
                            status, headers, None)
        got = Graph()
        got.parse(data=content)
        self.assertEqualGraphs(g, got)

    def test_extended_ntriples(self):
        # extended test 7: accept: "/data" + "text/plain" -> extended
        # RDF statements in NTriples
        self.env['PATH_INFO'] = self.env['PATH_INFO'] + "/data"       
        self.env['HTTP_ACCEPT'] = 'text/plain'
        g = Graph()
        g.parse(source=self.repo.store.distilled_path("123/a"))
        g += self.repo.annotation_file_to_graph(self.repo.store.annotation_path("123/a"))
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'text/plain'},
                            None,
                            status, headers, None)
        got = Graph()
        got.parse(data=content, format="nt")
        self.assertEqualGraphs(g, got)

    def test_extended_turtle(self):
        # extended test 7: accept: "/data" + "text/turtle" -> extended
        # RDF statements in Turtle
        self.env['PATH_INFO'] = self.env['PATH_INFO'] + "/data"       
        self.env['HTTP_ACCEPT'] = 'text/turtle'
        g = Graph()
        g.parse(source=self.repo.store.distilled_path("123/a"))
        g += self.repo.annotation_file_to_graph(self.repo.store.annotation_path("123/a"))
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'text/turtle'},
                            None,
                            status, headers, None)
        got = Graph()
        got.parse(data=content, format="turtle")
        self.assertEqualGraphs(g, got)


    def test_dataset_html(self):
        self.env['PATH_INFO'] = "/dataset/base"
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'text/html'},
                            b'<h1>TOC for base</h1>',
                            status, headers, content)

    def test_dataset_html_param(self):
        self.env['PATH_INFO'] = "/dataset/base"
        self.env['QUERY_STRING'] = "title=a"
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'text/html'},
                            b'<h1>Title starting with "a"</h1>',
                            status, headers, content)

    def test_dataset_ntriples(self):
        self.env['PATH_INFO'] = "/dataset/base"
        self.env['HTTP_ACCEPT'] = 'text/plain'
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'text/plain'},
                            None,
                            status, headers, None)
        want = Graph()
        want.parse(source="test/files/base/distilled/123/a.ttl",
                   format="turtle")
        got = Graph()
        got.parse(data=content, format="nt")
        self.assertEqualGraphs(want, got)

    def test_dataset_turtle(self):
        self.env['PATH_INFO'] = "/dataset/base"
        self.env['HTTP_ACCEPT'] = 'text/turtle'
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'text/turtle'},
                            None,
                            status, headers, None)
        want = Graph()
        want.parse(source="test/files/base/distilled/123/a.ttl",
                   format="turtle")
        got = Graph()
        got.parse(data=content, format="turtle")
        self.assertEqualGraphs(want, got)

    def test_dataset_xml(self):
        self.env['PATH_INFO'] = "/dataset/base"
        self.env['HTTP_ACCEPT'] = 'application/rdf+xml'
        status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'application/rdf+xml'},
                            None,
                            status, headers, None)
        want = Graph()
        want.parse(source="test/files/base/distilled/123/a.ttl",
                   format="turtle")
        got = Graph()
        got.parse(data=content, format="xml")
        self.assertEqualGraphs(want, got)


class Search(WSGI):

    def setUp(self):
        super(Search, self).setUp()
        self.env['PATH_INFO'] = '/mysearch/'

    def test_search_single(self):
        self.env['QUERY_STRING'] = "q=subsection"
        res = ([{'title': 'Result #1',
                 'uri': 'http://example.org',
                 'text': ['Text that contains the subsection term']}],
               {'pagenum': 1,
                'pagecount': 1,
                'firstresult': 1,
                'lastresult': 1,
                'totalresults': 1})
        
        config = {'connect.return_value': Mock(**{'query.return_value': res})}
        with patch('ferenda.manager.FulltextIndex', **config):
            status, headers, content = self.call_wsgi(self.env)
        t = etree.fromstring(content)
        resulthead = t.find(".//article/h1").text
        self.assertEqual(resulthead, "1 match for 'subsection'")



    def test_search_multiple(self):
        self.env['QUERY_STRING'] = "q=part"
        res = ([{'title':'Introduction',
                 'identifier': '123/a¶1',
                 'uri':'http://example.org/base/123/a#S1',
                 'text': html.P(['This is ',
                                 html.Strong(['part'], **{'class':'match'}),
                                 ' of document-',
                                 html.Strong(['part'], **{'class':'match'}),
                            ' section 1</p>'])},
                {#'title':'Definitions and Abbreviations',
                 'uri':'http://example.org/base/123/a#S2',
                 'text':html.P(['second main document ',
                                html.Strong(['part'], **{'class':'match'})])},
                {'title':'Example',
                 'uri':'http://example.org/base/123/a',
                 'text': html.P(['This is ',
                                 html.Strong(['part'], **{'class':'match'}),
                                 ' of the main document'])}],
               {'pagenum': 1,
                'pagecount': 1,
                'firstresult': 1,
                'lastresult': 3,
                'totalresults': 3})
        
        config = {'connect.return_value': Mock(**{'query.return_value': res})}
        with patch('ferenda.manager.FulltextIndex', **config):
            status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'text/html; charset=utf-8'},
                            None,
                            status, headers, None)

        t = etree.parse(BytesIO(content))
        css = t.findall("head/link[@rel='stylesheet']")
        self.assertEqual(len(css),4) # normalize, main, ferenda, and fonts.googleapis.com
        self.assertEqual('../rsrc/css/normalize-1.1.3.css',
                         css[0].get('href'))
        js = t.findall("head/script")
        self.assertEqual(len(js), 4) # jquery, modernizr, respond and ferenda
        
        resulthead = t.find(".//article/h1").text
        self.assertEqual(resulthead, "3 matches for 'part'")
        docs = t.findall(".//section[@class='hit']")
        self.assertEqual(len(docs), 3)
        self.assertEqual(docs[0][0].tag, 'h2')
        expect = res[0]
        self.assertIn(expect[0]['title'], docs[0][0][0].text)
        self.assertEqual(expect[0]['uri'], docs[0][0][0].get('href'))
        self.assertEqualXML(expect[0]['text'].as_xhtml(),
                            docs[0][1],
                            namespace_aware=False)

        self.assertIn(expect[1]['title'], docs[1][0][0].text)
        self.assertEqual(expect[1]['uri'], docs[1][0][0].get('href'))
        self.assertEqualXML(expect[1]['text'].as_xhtml(),
                            docs[1][1],
                            namespace_aware=False)
                         
        self.assertIn(expect[2]['title'], docs[2][0][0].text)
        self.assertEqual(expect[2]['uri'], docs[2][0][0].get('href'))
        self.assertEqualXML(expect[2]['text'].as_xhtml(),
                            docs[2][1],
                            namespace_aware=False)
                         

        
    def test_highlighted_snippet(self):
        res = ([{'title':'Example',
                 'uri':'http://example.org/base/123/b1',
                 'text':html.P(['sollicitudin justo ',
                                html.Strong(['needle'], **{'class':'match'}),
                                ' tempor ut eu enim ... himenaeos. ',
                                html.Strong(['Needle'], **{'class':'match'}),
                                ' id tincidunt orci'])}],
               {'pagenum': 1,
                'pagecount': 1,
                'firstresult': 1,
                'lastresult': 1,
                'totalresults': 1})

        self.env['QUERY_STRING'] = "q=needle"
        config = {'connect.return_value': Mock(**{'query.return_value': res})}
        with patch('ferenda.manager.FulltextIndex', **config):
            status, headers, content = self.call_wsgi(self.env)
        
        self.assertResponse("200 OK",
                            {'Content-Type': 'text/html; charset=utf-8'},
                            None,
                            status, headers, None)
        
        t = etree.fromstring(content)
        docs = t.findall(".//section[@class='hit']")
        self.assertEqualXML(res[0][0]['text'].as_xhtml(),
                            docs[0][1],
                            namespace_aware=False)

    def test_paged(self):
        def mkres(page=1, pagesize=10, total=25):
            hits = []
            for i in range((page-1)*pagesize, min(page*pagesize, total)):
                hits.append(
                    {'title':'',
                     'uri':'http://example.org/base/123/c#S%d'% ((i*2)-1),
                     'text': html.P(['This is a needle document'])})
            return (hits,
                    {'pagenum': page,
                     'pagecount': int(total / pagesize) + 1,
                     'firstresult': (page - 1) * pagesize + 1,
                     'lastresult': (page - 1) * pagesize + len(hits),
                     'totalresults': total})
                
            
        self.env['QUERY_STRING'] = "q=needle"
        res = mkres()
        
        config = {'connect.return_value': Mock(**{'query.return_value': res})}
        with patch('ferenda.manager.FulltextIndex', **config):
            status, headers, content = self.call_wsgi(self.env)
        self.assertResponse("200 OK",
                            {'Content-Type': 'text/html; charset=utf-8'},
                            None,
                            status, headers, None)                            
        
        t = etree.fromstring(content)
        docs = t.findall(".//section[@class='hit']")
        self.assertEqual(10, len(docs)) # default page size (too small?)
        pager = t.find(".//div[@class='pager']")
        
        # assert that pager looks smth like this:
        # <div class="pager">
        #   <p class="label">Results 1-10 of 25</p>
        #   <span class="page">1</span>
        #   <a href="/mysearch/?q=needle&p=2" class="page">2</a>
        #   <a href="/mysearch/?q=needle&p=3" class="page">3</a>
        # </div>
        self.assertEqual(4,len(pager))
        self.assertEqual('p',pager[0].tag)
        self.assertEqual('Results 1-10 of 25',pager[0].text)
        self.assertEqual('span',pager[1].tag)
        self.assertEqual('a',pager[2].tag)
        self.assertEqual('/mysearch/?q=needle&p=2',pager[2].get('href'))

        self.env['QUERY_STRING'] = "q=needle&p=2"
        res = mkres(page=2)
        config = {'connect.return_value': Mock(**{'query.return_value': res})}
        with patch('ferenda.manager.FulltextIndex', **config):
            status, headers, content = self.call_wsgi(self.env)
        t = etree.fromstring(content)
        docs = t.findall(".//section[@class='hit']")
        self.assertEqual(10, len(docs)) 
        pager = t.find(".//div[@class='pager']")
        self.assertEqual(4,len(pager))
        self.assertEqual('Results 11-20 of 25',pager[0].text)
        self.assertEqual('/mysearch/?q=needle&p=1',pager[1].get('href'))

        self.env['QUERY_STRING'] = "q=needle&p=3"
        res = mkres(page=3)
        config = {'connect.return_value': Mock(**{'query.return_value': res})}
        with patch('ferenda.manager.FulltextIndex', **config):
            status, headers, content = self.call_wsgi(self.env)
        t = etree.fromstring(content)
        docs = t.findall(".//section[@class='hit']")
        self.assertEqual(5, len(docs)) # only 5 remaining docs
        pager = t.find(".//div[@class='pager']")
        self.assertEqual(4,len(pager))
        self.assertEqual('Results 21-25 of 25',pager[0].text)


#================================================================
# AdvancedAPI test case
#        
# This advaced API test framework uses three docrepos. Each docrepo is
# slightly different in what kind of documents it contains and which
# metadata is stored about each one. (This setup is similar to
# integrationFulltextIndex and the DocRepo1/DocRepo2 , but, you know,
# different...)

class DocRepo1(DocumentRepository):
    # this has the default set of facets (rdf:type, dct:title,
    # dct:publisher, dct:issued) and a number of documents such as
    # each bucket in the facet has 2-1-1 facet values
    # 
    #   rdf:type         dct:title       dct:publisher dct:issued
    # A ex:MainType     "A simple doc"   ex:publ1      2012-04-01
    # B ex:MainType     "Other doc"      ex:publ2      2013-06-06
    # C ex:OtherType    "More docs"      ex:publ2      2014-05-06
    # D ex:YetOtherType "Another doc"    ex:publ3      2014-09-23
    alias = "repo1"

class DocRepo2(DocumentRepository):
    # this repo contains facets that excercize all kinds of fulltext.IndexedType objects
    alias = "repo2"
    def facets():
        return [Facet(RDF.type),       # fulltextindex.URI
                Facet(DCT.title),      # fulltextindex.Text(boost=4)
                Facet(DCT.identifier), # fulltextindex.Label(boost=16)
                Facet(DCT.issued),     # fulltextindex.Datetime()
                Facet(DCT.publisher),  # fulltextindex.Resource()
                Facet(DC.subject),     # fulltextindex.Keywords()
                Facet(SCHEMA.free)     # fulltextindex.Boolean()
                ]

class DocRepo3(DocumentRepository):
    # this repo contains custom facets with custom selectors/keys,
    # unusual predicates like DC.publisher, and non-standard
    # configuration like a title not used for toc (and toplevel only)
    # or DCT.creator for each subsection, or DCT.publisher w/ multiple=True
    alias = "repo3"
    def my_id_selector(self, row, binding, graph):
        # categorize each ID after the number of characters in it
        return str(len(row[binding]))

    def lexicalkey(self, row, binding): # , graph
        return "".join(row[binding].lower().split())
    
    def facets(self):
        return [Facet(DC.publisher),
                Facet(DCT.issued, indexingtype=fulltextindex.Label()),
                Facet(DCT.rightsHolder, indexingtype=fulltextindex.Resources(), multiple_values=True),
                Facet(DCT.title, toplevel_only=True),
                Facet(DCT.identifer, selector=self.my_id_selector(), key=self.lexicalkey, label="IDs having %(selected) characters"),
                Facet(DC.creator, toplevel_only=False)]


class AdvancedAPI(WSGI):

    ts_type = 'FUSEKI'
    ts_location = 'http://localhost:3030/'
    ts_repository = 'ds'
    ft_type = 'ELASTICSEARCH'
    ft_location = 'http://localhost:9200'
    ft_repos = (DocRepo1(), DocRepo2(), DocRepo3())

    def put_files_in_place(self):
        for repoclass in DocRepo1, DocRepo2, DocRepo3:
            repo = repoclass(datadir = self.datadir)
            for basefile in "a", "b", "c", "d":
                util.ensure_dir(repo.store.parsed_path(basefile))
                # Put files in place: parsed
                parsed_path = "test/files/testrepos/%s/parsed/%s.xhtml" % (repo.alias, basefile)
                shutil.copy2(parsed_path, self.repo.store.parsed_path(basefile))

                # FIXME: This distilling code is copied from
                # decorators.render -- should perhaps move to a
                # DocumentRepository method like render_xhtml
                distilled_graph = Graph()
                with codecs.open(repo.store.parsed_path(basefile),
                                 encoding="utf-8") as fp:  # unicode
                    distilled_graph.parse(data=fp.read(), format="rdfa",
                                          publicID=repo.canonical_uri(basefile))
                distilled_graph.bind("dc", URIRef("http://purl.org/dc/elements/1.1/"))
                distilled_graph.bind("dct", URIRef("http://example.org/this-prefix-should-not-be-used"))
                util.ensure_dir(self.store.distilled_path(doc.basefile))
                with open(self.store.distilled_path(doc.basefile),
                          "wb") as distilled_file:
                    distilled_graph.serialize(distilled_file, format="pretty-xml")

                # finally index all the data into the triplestore/fulltextindex
                repo.relate(basefile)

    #def test_basic(self):
    #    pass
