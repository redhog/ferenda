# -*- coding: utf-8 -*-
"""Most of these decorators are intended to handle various aspects of
a complete :py:meth:`~ferenda.DocumentRepository.parse`
implementation. Normally you should only use the
:py:func:`~ferenda.decorators.managedparsing` decorator (if you even
override the basic implementation). If you create separate actions
aside from the standards (``download``, ``parse``, ``generate`` et
al), you should also use :py:func:`~ferenda.decorators.action` so that
manage.py will be able to call it.
"""
from __future__ import (absolute_import, division,
                        print_function, unicode_literals)
from builtins import *

from datetime import datetime
from traceback import format_tb
from io import StringIO
import codecs
import functools
import itertools
import os
import sys
import time
import logging

from rdflib import Graph, URIRef
from rdflib.compare import graph_diff
from layeredconfig import LayeredConfig

from ferenda import util
from ferenda import DocumentEntry
from ferenda.errors import DocumentRemovedError, ParseError
from ferenda.elements import serialize


def timed(f):
    """Automatically log a statement of how long the function call takes"""
    @functools.wraps(f)
    def wrapper(self, doc):
        start = time.time()
        ret = f(self, doc)
        # FIXME: We shouldn't log this if we don't actually do any
        # work. The easiest way is to make sure parseifneeded wraps
        # timed, not the other way round.

        # ALSO: the addition of "parse" here makes the decorator only
        # useful for the parse method. It'd be better to have the
        # decorator take a format string and a method to call to
        # log. But maybe the util.logtime context manager is better
        # suited for this usecase?
        if isinstance(self.config.processes, int) and self.config.processes > 1:
            self.log.info(
                '%s: parse OK (%.3f sec) [pid %s]',
                doc.basefile,
                time.time() - start,
                os.getpid())
        else:
            self.log.info('%s: parse OK (%.3f sec)', doc.basefile, time.time() - start)
        return ret
    return wrapper


def recordlastdownload(f):
    """Automatically stores current time in ``self.config.lastdownload``
    """
    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
        ret = f(self, *args, **kwargs)
        # only update the lastdownload for full downloads (if no
        # specific basefile was specified)
        if not args:
            self.config.lastdownload = datetime.now()
            LayeredConfig.write(self.config)
        return ret
    return wrapper


def parseifneeded(f):
    """Makes sure the parse function is only called if needed, i.e. if
    the outfile is nonexistent or older than the infile(s), or if the
    user has specified in the config file or on the command line that
    it should be re-generated."""
    @functools.wraps(f)
    def wrapper(self, basefile):
        # note: We hardcode the use of .parseneeded() and the
        # 'parseforce' config option, which means that this decorator
        # can only be used sensibly with the .parse() function.
        force = (self.config.force is True or
                 self.config.parseforce is True)
        if not force and not self.parseneeded(basefile):
            self.log.debug("%s: Skipped", basefile)
            return True  # Signals that everything is OK
        else:
            self.log.debug("%s: Starting", basefile)
            return f(self, basefile)
    return wrapper

def updateentry(f):

    @functools.wraps(f)
    def wrapper(self, basefile):
        def clear(key, d):
            if key in d:
                del d[key]
        logstream = StringIO()
        handler = logging.StreamHandler(logstream)
        # FIXME: Think about which format is optimal for storing in
        # docentry. Do we need eg name and levelname? Should we log
        # date as well as time?
        fmt = "%(asctime)s %(name)s %(levelname)s %(message)s"
        formatter = logging.Formatter(fmt, datefmt="%H:%M:%S")
        handler.setFormatter(formatter)
        handler.setLevel(logging.WARNING)
        rootlog = logging.getLogger()
        rootlog.addHandler(handler)
        start = datetime.now()
        try:
            ret = f(self, basefile)
            success = True
        except Exception as e:
            success = False
            errortype, errorval, errortb = sys.exc_info()
            raise
        except KeyboardInterrupt as e:
            success = None
            raise
        else:
            return ret
        finally:
            rootlog.removeHandler(handler)
            if success is not None:
                warnings = logstream.getvalue()
                entry = DocumentEntry(self.store.documententry_path(basefile))
                entry.parse['success'] = success
                entry.parse['date'] = start
                delta = datetime.now()-start
                try:
                    duration = delta.total_seconds()
                except AttributeError:
                    # probably on py26, wich lack total_seconds()
                    duration = delta.seconds + (delta.microseconds / 1000000.0)
                entry.parse['duration'] = duration
                if warnings:
                    entry.parse['warnings'] = warnings
                else:
                    clear('warnings', entry.parse)
                if not success:
                    entry.parse['traceback'] = "".join(format_tb(errortb))
                    entry.parse['error'] = "%s: %s (%s)" % (errorval.__class__.__name__,
                                                            errorval, util.location_exception(errorval))
                else:
                    clear('traceback', entry.parse)
                    clear('error', entry.parse)
                entry.save()
    return wrapper


def render(f):
    """Handles the serialization of the :py:class:`~ferenda.Document`
    object to XHTML+RDFa and RDF/XML files. Must be used in
    conjunction with :py:func:`~ferenda.decorators.makedocument`.

    """
    # NOTE: The actual rendering is two lines of code. The bulk of
    # this function validates that the XHTML+RDFa file that we end up
    # with contains the exact same triples as is present in the doc
    # object (including both the doc.meta Graph and any other Graph
    # that might be present on any doc.body object). Also, this func
    # validates taht the documententry file has been properly filled,
    # which is sort of outside of the responsibility of this func,
    # but...

    def iterate_graphs(node):
        res = []
        if hasattr(node, 'meta') and node.meta is not None:
            res.append(node.meta)
        try:
            for subnode in node:
                if not isinstance(subnode, str):
                    res.extend(iterate_graphs(subnode))
        except TypeError:  # node was not iterable
            pass
        return res

    @functools.wraps(f)
    def wrapper(self, doc):
        # call the actual function that creates the doc data
        ret = f(self, doc)
        # now render thath doc data as files (JSON, XHTML, RDF/XML)
        if self.config.serializejson == True:
            with self.store.open_serialized(doc.basefile, "wb") as fp:
                r = serialize(doc, format="json")  # should be a (unicode) str
                fp.write(r.encode('utf-8'))
            self.log.debug(
                "%s: Created %s" %
                (doc.basefile,
                 self.store.serialized_path(
                     doc.basefile)))

        updated = self.render_xhtml(doc, self.store.parsed_path(doc.basefile))
        if updated:
            self.log.debug(
                "%s: Created %s" %
                (doc.basefile,
                 self.store.parsed_path(
                     doc.basefile)))

        # css file + background images + png renderings of text
        self.create_external_resources(doc)

        # Extract all triples on the XHTML/RDFa data to a separate
        # RDF/XML file
        distilled_graph = Graph()
        with codecs.open(self.store.parsed_path(doc.basefile),
                         encoding="utf-8") as fp:  # unicode
            distilled_graph.parse(data=fp.read(), format="rdfa",
                                  publicID=doc.uri)

        # The act of parsing from RDFa binds a lot of namespaces
        # in the graph in an unneccesary manner. Particularly it
        # binds both 'dc' and 'dcterms' to
        # 'http://purl.org/dc/terms/', which makes serialization
        # less than predictable. Blow these prefixes away.
        distilled_graph.bind("dc", URIRef("http://purl.org/dc/elements/1.1/"))
        distilled_graph.bind(
            "dcterms",
            URIRef("http://example.org/this-prefix-should-not-be-used"))

        util.ensure_dir(self.store.distilled_path(doc.basefile))
        with open(self.store.distilled_path(doc.basefile),
                  "wb") as distilled_file:
            # print("============distilled===============")
            # print(distilled_graph.serialize(format="turtle").decode('utf-8'))
            distilled_graph.serialize(distilled_file, format="pretty-xml")
        self.log.debug(
            '%s: %s triples extracted to %s', doc.basefile,
            len(distilled_graph), self.store.distilled_path(doc.basefile))

        # Validate that all required triples are present (we check
        # distilled_graph, but we could just as well check doc.meta)
        for p in self.required_predicates:
            x = distilled_graph.value(URIRef(doc.uri), p)
            if not x:
                self.log.warning("%s: Metadata is missing a %s triple" %
                                 (doc.basefile, distilled_graph.qname(p)))

        # Validate that all triples specified in doc.meta and any
        # .meta property on any body object is present in the
        # XHTML+RDFa file.  NOTE: graph_diff has suddenly become
        # glacial on large graphs (~10000 triples). Maybe we don't
        # have to validate them?
        huge_graph = False
        for g in iterate_graphs(doc.body):
            doc.meta += g
            if len(doc.meta) > 3000:
                huge_graph = True
                break
        if huge_graph:
            self.log.warning("%s: Graph seems huge, skipping validation" % doc.basefile)
        else:
            # self.log.debug("%s: diffing graphs" % doc.basefile)
            (in_both, in_first, in_second) = graph_diff(doc.meta, distilled_graph)
            self.log.debug("%s: graphs diffed (-%s, +%s)" % (doc.basefile, len(in_first), len(in_second)))

            if in_first:  # original metadata not present in the XHTML filee
                self.log.warning("%s: %d triple(s) from the original metadata was "
                                 "not found in the serialized XHTML file:\n%s",
                                 doc.basefile, len(in_first), in_first.serialize(format="n3").decode("utf-8"))

        # Validate that entry.title and entry.id has been filled
        # (might be from doc.meta and doc.uri, might be other things
        entry = DocumentEntry(self.store.documententry_path(doc.basefile))
        if not entry.id:
            self.log.warning("%s: entry.id missing" % doc.basefile)
        if not entry.title:
            self.log.warning("%s: entry.title missing" % doc.basefile)
        return ret
    return wrapper


def handleerror(f):
    """Make sure any errors in :py:meth:`ferenda.DocumentRepository.parse`
    are handled appropriately and do not stop the parsing of all documents.
    """
    @functools.wraps(f)
    def wrapper(self, doc):
        try:
            return f(self, doc)
        except DocumentRemovedError as e:
            self.log.info(
                "%s: Document has been removed (%s)", doc.basefile, e)
            util.robust_remove(self.parsed_path(doc.basefile))
            return False
        except ParseError as e:
            self.log.error("%s: ParseError %s", doc.basefile, e)
            # FIXME: we'd like to use the shorter "if
            # ('fatalexceptions' in self.config" but a Mock we're
            # using in testDecorators.Decorators.test_handleerror does
            # not emulate this way of using the LayeredConfig
            # object. Until we rewrite the testcase better, this is
            # what we have to do.
            if (hasattr(self.config, 'fatalexceptions') and
                    self.config.fatalexceptions):
                raise
            else:
                return False
        except Exception:
            self.log.exception("parse of %s failed", doc.basefile)
            # FIXME: see above
            if (hasattr(self.config, 'fatalexceptions') and
                    self.config.fatalexceptions):
                raise
            else:
                return False
    return wrapper


def makedocument(f):
    """Changes the signature of the parse method to expect a Document
    object instead of a basefile string, and creates the object."""
    @functools.wraps(f)
    def wrapper(self, basefile):
        doc = self.make_document(basefile)
        return f(self, doc)
    return wrapper


def managedparsing(f):
    """Use all standard decorators for parse() in the correct order
    (:py:func:`~ferenda.decorators.parseifneeded`, 
    :py:func:`~ferenda.decorators.makedocument`, 
    :py:func:`~ferenda.decorators.timed`, 
    :py:func:`~ferenda.decorators.render`)"""
    return parseifneeded(
        updateentry(
            makedocument(
                # handleerror( # is this really a good idea?
                timed(
                    render(f)))))


def action(f):
    """Decorator that marks a class or instance method as runnable by
    :py:func:`ferenda.manager.run`
    """
    f.runnable = True
    return f


def downloadmax(f):
    """Makes any generator respect the ``downloadmax`` config parameter.

    """
    @functools.wraps(f)
    def wrapper(self, params):
        if 'downloadmax' in self.config:
            self.log.info("Downloading max %d documents" %
                          (self.config.downloadmax))
            generator = itertools.islice(f(self, params),
                                         self.config.downloadmax)
        else:
            self.log.debug("Downloading all the docs")
            generator = f(self, params)
        for value in generator:
            yield value
    return wrapper


def newstate(state):
    def real_decorator(f):
        setattr(f, 'newstate', state)
        return f
    return real_decorator
