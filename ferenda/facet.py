# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

import logging
from datetime import datetime

from six import text_type as str
from rdflib import URIRef, Namespace
from rdflib.namespace import RDF, RDFS, DC, SKOS, FOAF, DCTERMS
SCHEMA = Namespace("http://schema.org/")

from ferenda import fulltextindex # to get the IndexedType classes
from ferenda import util

class Facet(object):
    """Create a facet from the given rdftype and some optional parameters.

    :param rdftype: The type of facet being created
    :type rdftype: rdflib.term.URIRef
    :param label: TBW
    :param pagetitle: TBW
    :param indexingtype: TBW
    :param selector: TBW
    :param key: TBW
    :param toplevel_only: TBW
    :param use_for_toc: TBW
    :param selector_descending: TBW
    :param key_descending: TBW
    :param multiple_values: TBW
    :param dimension_type: TBW
    :param dimension_label: TBW
    :param identificator: TBW

    If optional parameters aren't given, then appropriate values are
    selected if rdfrtype is one of some common rdf properties:

    ===================  ======================================================
    facet                description
    ===================  ======================================================
    rdf:type             Grouped by :py:meth:`~rdflib.graph.Graph.qname` of the
                         ``rdf:type`` of the document, eg. ``foaf:Document``.
                         Not used for toc
    -------------------  ------------------------------------------------------
    dcterms:title        Grouped by first "sortable" letter, eg for a document
                         titled "The Little Prince" returns "l". Is used as a
                         facet for the API, but it's debatable if it's useful
    -------------------  ------------------------------------------------------
    dcterms:identifier   Also grouped by first sortable letter. When indexing,
                         the resulting fulltext index field has a high boost
                         value, which increases the chances of this document
                         ranking high when one searches for its identifier.
    -------------------  ------------------------------------------------------
    dcterms:abstract     Not used for toc
    -------------------  ------------------------------------------------------
    dc:creator           Should be a free-test (string literal) value
    -------------------  ------------------------------------------------------
    dcterms:publisher    Should be a URIRef
    -------------------  ------------------------------------------------------
    dcterms:references   
    -------------------  ------------------------------------------------------
    dcterms:issued       Used for grouping documents published/issued in the
                         same year
    -------------------  ------------------------------------------------------
    dc:subject           A document can have multiple dc:subjects and all are
                         indexed/processed
    -------------------  ------------------------------------------------------
    dcterms:subject      Works like dc:subject, but the value should be a
                         URIRef
    -------------------  ------------------------------------------------------
    schema:free          A boolean value
    ===================  ======================================================

    This module contains a number of classmethods that can be used as
    arguments to ``selector`` and ``key``, eg

    >>> from rdflib import Namespace
    >>> MYVOCAB = Namespace("http://example.org/vocab/")
    >>> f = Facet(MYVOCAB.enactmentDate, selector=Facet.year)
    >>> f.selector({'myvocab_enactmentDate': '2014-07-06'},
    ...            'myvocab_enactmentDate')
    '2014'

    """
        

    @classmethod
    def defaultselector(cls, row, binding, resource_graph=None):

        """This returns ``row[binding]`` without any transformation.
    
        >>> row = {"rdf_type": "http://purl.org/ontology/bibo/Book",
        ...        "dcterms_title": "A Tale of Two Cities",
        ...        "dcterms_issued": "1859-04-30",
        ...        "dcterms_publisher": "http://example.org/chapman_hall",
        ...        "schema_free": "true"}
        >>> Facet.defaultselector(row, "dcterms_title")
        'A Tale of Two Cities'
        """
        return row[binding]

    @classmethod
    def year(cls, row, binding='dcterms_issued', resource_graph=None):
        """This returns the the year part of ``row[binding]``.

        >>> row = {"rdf_type": "http://purl.org/ontology/bibo/Book",
        ...        "dcterms_title": "A Tale of Two Cities",
        ...        "dcterms_issued": "1859-04-30",
        ...        "dcterms_publisher": "http://example.org/chapman_hall",
        ...        "schema_free": "true"}
        >>> Facet.year(row, "dcterms_issued")
        '1859'
        """
        datestring = row[binding]
        # assume a date(time) like '2014-06-05T12:00:00', '2014-06-05'
        # or even '2014-06'
        formatstring = {19: "%Y-%m-%dT%H:%M:%S",
                        10: "%Y-%m-%d",
                        7: "%Y-%m"}[len(datestring)]
        d = datetime.strptime(datestring, formatstring)
        return str(d.year)

    @classmethod
    def booleanvalue(cls, row, binding='schema_free', resource_graph=None):
        """
        Returns True iff row[binding] == "true", False otherwise.
        
        >>> row = {"rdf_type": "http://purl.org/ontology/bibo/Book",
        ...        "dcterms_title": "A Tale of Two Cities",
        ...        "dcterms_issued": "1859-04-30",
        ...        "dcterms_publisher": "http://example.org/chapman_hall",
        ...        "schema_free": "true"}
        >>> Facet.booleanvalue(row, "schema_free")
        True
        """
        # only 'true' is True, everything else is False
        return row[binding] == 'true'

        
    @classmethod
    def titlesortkey(cls, row, binding='dcterms_title', resource_graph=None):
        """Returns a version of row[binding] suitable for sorting. The
        function :py:func:`~ferenda.util.title_sortkey` is used for
        string transformation.
        
        >>> row = {"rdf_type": "http://purl.org/ontology/bibo/Book",
        ...        "dcterms_title": "A Tale of Two Cities",
        ...        "dcterms_issued": "1859-04-30",
        ...        "dcterms_publisher": "http://example.org/chapman_hall",
        ...        "schema_free": "true"}
        >>> Facet.titlesortkey(row, "dcterms_title")
        'ataleoftwocities'

        """
        True
        # ignore provided binding -- this key func sorts by
        # dcterms:title, period.
        # FIXME: Why was that, now again?
        title = row['dcterms_title']
        return util.title_sortkey(title)

    @classmethod
    def firstletter(cls, row, binding='dcterms_title', resource_graph=None):
        """Returns the first letter of row[binding], transformed into a
        sortable string.
        
        >>> row = {"rdf_type": "http://purl.org/ontology/bibo/Book",
        ...        "dcterms_title": "A Tale of Two Cities",
        ...        "dcterms_issued": "1859-04-30",
        ...        "dcterms_publisher": "http://example.org/chapman_hall",
        ...        "schema_free": "true"}
        >>> Facet.firstletter(row, "dcterms_title")
        'a'

        """
        return cls.titlesortkey(row, binding)[0]

    @classmethod
    def resourcelabel(cls, row, binding='dcterms_publisher', resource_graph=None):
        """Lookup a suitable text label for row[binding] in resource_graph.
        
        >>> row = {"rdf_type": "http://purl.org/ontology/bibo/Book",
        ...        "dcterms_title": "A Tale of Two Cities",
        ...        "dcterms_issued": "1859-04-30",
        ...        "dcterms_publisher": "http://example.org/chapman_hall",
        ...        "schema_free": "true"}
        >>> import rdflib
        >>> resources = rdflib.Graph().parse(format="turtle", data=\"""
        ... @prefix foaf: <http://xmlns.com/foaf/0.1/> .
        ... 
        ... <http://example.org/chapman_hall> a foaf:Organization;
        ...     foaf:name "Chapman & Hall" .
        ... 
        ... \""")
        >>> Facet.resourcelabel(row, "dcterms_publisher", resources)
        'Chapman & Hall'
        """
        uri = URIRef(row[binding])
        for pred in (RDFS.label, SKOS.prefLabel, SKOS.altLabel, DCTERMS.title, DCTERMS.alternative, FOAF.name):
            if resource_graph.value(uri, pred):
                return str(resource_graph.value(uri, pred))
        else:
            return row[binding]

    @classmethod
    def sortresource(cls, row, binding='dcterms_publisher', resource_graph=None):
        """Returns a sortable version of the resource label for
        ``row[binding]``.

        >>> row = {"rdf_type": "http://purl.org/ontology/bibo/Book",
        ...        "dcterms_title": "A Tale of Two Cities",
        ...        "dcterms_issued": "1859-04-30",
        ...        "dcterms_publisher": "http://example.org/chapman_hall",
        ...        "schema_free": "true"}
        >>> import rdflib
        >>> resources = rdflib.Graph().parse(format="turtle", data=\"""
        ... @prefix foaf: <http://xmlns.com/foaf/0.1/> .
        ... 
        ... <http://example.org/chapman_hall> a foaf:Organization;
        ...     foaf:name "Chapman & Hall" .
        ... 
        ... \""")
        >>> Facet.sortresource(row, "dcterms_publisher", resources)
        'chapmanhall'
        """
        row[binding] = cls.resourcelabel(row, binding, resource_graph)
        # workaround the way titlesortkey works
        return cls.titlesortkey({'dcterms_title': row[binding]}, binding)


    @classmethod
    def term(cls, row, binding='dcterms_publisher', resource_graph=None):
        """Returns the leaf part of the URI found in ``row[binding]``.

        >>> row = {"rdf_type": "http://purl.org/ontology/bibo/Book",
        ...        "dcterms_title": "A Tale of Two Cities",
        ...        "dcterms_issued": "1859-04-30",
        ...        "dcterms_publisher": "http://example.org/chapman_hall",
        ...        "schema_free": "true"}
        >>> Facet.term(row, "dcterms_publisher")
        'chapman_hall'
        """
        return util.uri_leaf(row[binding])

    @classmethod
    def qname(cls, row, binding='rdf_type', resource_graph=None):
        """Returns the qname of the rdf URIref contained in row[binding], as
        determined by the namespace prefixes registered in
        resource_graph.

        >>> row = {"rdf_type": "http://purl.org/ontology/bibo/Book",
        ...        "dcterms_title": "A Tale of Two Cities",
        ...        "dcterms_issued": "1859-04-30",
        ...        "dcterms_publisher": "http://example.org/chapman_hall",
        ...        "schema_free": "true"}
        >>> import rdflib
        >>> resources = rdflib.Graph()
        >>> resources.bind("bibo", "http://purl.org/ontology/bibo/")
        >>> Facet.qname(row, "rdf_type", resources)
        'bibo:Book'
        """
        u = URIRef(row[binding])
        return resource_graph.qname(u)

    # define a number of default values, used if the user does not
    # explicitly specify indexingtype/selector/key
    defaults = None
    # formatting directives for label/pagetitle:
    # %(criteria)s = The human-readable criteria for sorting/dividing/faceting, eg "date of publication", "document title" or "publisher"
    # %(selected)s = The selected value, eg "2014", "A", "O'Reilly and Associates Publishing, inc."
    # %(selected_uri)s = For resource-type values, the underlying URI, eg "http://example.org/ext/publisher/oreilly"
    def __init__(self,
                 rdftype=DCTERMS.title, # any rdflib.URIRef -- should be called 'rdfpredicate'??
                 label=None, # toclabel
                 pagetitle=None, 
                 indexingtype=None,   # if not given, determined by rdftype
                 selector=None,       # - "" -
                 key=None,            # - "" -
                 identificator=None,  # - "" - (normally same as selector)
                 toplevel_only=None,  # - "" -
                 use_for_toc=None,    # - "" -
                 selector_descending = None,
                 key_descending = None,
                 multiple_values = None,
                 dimension_type = None, # could be determined by indexingtype
                 dimension_label = None
             ):
        
        def _finddefault(provided, rdftype, argumenttype, default):
            if provided is None:
                if rdftype in self.defaults and argumenttype in self.defaults[rdftype]:
                    return self.defaults[rdftype][argumenttype]
                else:
                    # since self.defaults doesn't contain meaningless
                    # defaults (like selector for rdf:type) it's not a
                    # good UI to warn about this. Might need to add
                    # more data to self.defaults in order to re-enable
                    # this.

                    # log = logging.getLogger(__name__)
                    # log.warning("Cannot map rdftype %s with argumenttype %s, defaulting to %r" %
                    #             (rdftype, argumenttype, default))
                    return default                
            else:
                return provided

        self.rdftype = rdftype
        self.label = _finddefault(label, rdftype, 'label', "Sorted by %(term)s")
        self.pagetitle = _finddefault(pagetitle, rdftype, 'pagetitle', "Documents where %(term)s = %(selected)s")
        self.indexingtype        = _finddefault(indexingtype, rdftype, 'indexingtype', fulltextindex.Text())
        self.selector            = _finddefault(selector, rdftype, 'selector', self.defaultselector)
        self.key                 = _finddefault(key, rdftype, 'key', self.defaultselector)
        self.identificator       = _finddefault(identificator, rdftype, 'identificator', self.defaultselector)
        self.toplevel_only       = _finddefault(toplevel_only, rdftype, 'toplevel_only', False)
        self.use_for_toc         = _finddefault(use_for_toc, rdftype, 'use_for_toc', False)
        self.selector_descending = _finddefault(selector_descending, rdftype, 'selector_descending', False)
        self.key_descending      = _finddefault(key_descending, rdftype, 'key_descending', False)
        self.multiple_values     = _finddefault(multiple_values, rdftype, 'multiple_values', False)
        self.dimension_type      = _finddefault(dimension_type, rdftype, 'dimension_type', None)
        # dimension_label should only be provided if an unusual
        # selector for a rdftype is used (eg is_april_fools() for
        # dcterms:issued), therefore no rdftype-dependent default.
        self.dimension_label     = dimension_label

    def __repr__(self):
        dictrepr = "".join((" %s=%r" % (k, v) for k, v in sorted(self.__dict__.items()) if not callable(v)))
        return ("<%s%s>" % (self.__class__.__name__, dictrepr))
        
    def __eq__(self, other):
        # compare only those properties that affects the SET of
        # selected data using this facet
        return (self.rdftype == other.rdftype and
                self.dimension_type == other.dimension_type and
                self.dimension_label == other.dimension_label and 
                self.selector == other.selector)

        
Facet.defaults = {RDF.type: {
                      'indexingtype': fulltextindex.URI(),
                      'toplevel_only': False,
                      'use_for_toc': False,
                      'selector': Facet.qname,
                      'identificator': Facet.term,
                      'dimension_type': "term"},
                  DCTERMS.title: {
                      'indexingtype': fulltextindex.Text(boost=4),
                      'toplevel_only': False,
                      'use_for_toc': True, 
                      'selector': Facet.firstletter,
                      'key': Facet.titlesortkey,
                      'identificator': Facet.firstletter,
                      'dimension_type': "value",
                      'pagetitle': 'Documents starting with "%(selected)s"'
                  },
                  DCTERMS.identifier: {
                      'indexingtype': fulltextindex.Label(boost=16),
                      'toplevel_only': False,
                      'use_for_toc': True, 
                      'selector': Facet.firstletter,
                      'key': Facet.titlesortkey,
                      'identificator': Facet.firstletter,
                  },
                  DCTERMS.abstract: {
                      'indexingtype': fulltextindex.Text(boost=2),
                      'toplevel_only': True,
                      'use_for_toc': False
                  },
                  DC.creator:{
                      'indexingtype': fulltextindex.Label(),
                      'toplevel_only': True,
                      'use_for_toc': True,
                      'selector': Facet.defaultselector,
                      'key': Facet.titlesortkey,
                      'dimension_type': "value"
                  },
                  DCTERMS.publisher:{
                      'indexingtype': fulltextindex.Resource(),
                      'toplevel_only': True,
                      'use_for_toc': True,
                      'selector': Facet.resourcelabel,
                      'key': Facet.resourcelabel,
                      'identificator': Facet.term,
                      'dimension_type': 'ref',
                  },
                  DCTERMS.references:{ # NB: this is a single URI reference w/o label
                      'indexingtype': fulltextindex.URI(),
                      'use_for_toc': False,
                  },
                  DCTERMS.issued:{
                      'label': "Sorted by publication year",
                      'pagetitle': "Documents published in %(selected)s",
                      'indexingtype': fulltextindex.Datetime(),
                      'toplevel_only': True,
                      'use_for_toc': True,
                      'selector': Facet.year,
                      'key': Facet.defaultselector,
                      'identificator': Facet.year,
                      'selector_descending': False,
                      'key_descending': False,
                      'dimension_type': "year"
                  },
                  DC.subject: {
                      'indexingtype': fulltextindex.Keyword(),  # eg. one or more string literals (not URIRefs),
                      'multiple_values': True,
                      'toplevel_only': True,
                      'use_for_toc': True,
                      'selector': Facet.defaultselector,
                      'key': Facet.defaultselector,
                      'multiple_values': True,
                      'dimension_type': 'value',
                },
                DCTERMS.subject: {
                    'indexingtype': fulltextindex.Resource(),  # eg. one or more URIRefs + labels
                    'multiple_values': True,
                    'toplevel_only': True,
                    'use_for_toc': True,
                    'selector': Facet.resourcelabel,
                    'key': Facet.resourcelabel,
                    'identificator': Facet.term,
                    'multiple_values': True,
                    'dimension_type': 'value',
                },
                SCHEMA.free: { # "A flag to signal that the publication is accessible for free."
                    'indexingtype': fulltextindex.Boolean(),
                    'toplevel_only': True,
                    'use_for_toc': True,
                    'selector': Facet.booleanvalue,
                    'key': Facet.defaultselector,
                    'dimension_type': 'value'
                }
            }
