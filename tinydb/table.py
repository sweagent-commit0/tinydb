"""
This module implements tables, the central place for accessing and manipulating
data in TinyDB.
"""
from typing import Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Union, cast, Tuple
from .queries import QueryLike
from .storages import Storage
from .utils import LRUCache
__all__ = ('Document', 'Table')

class Document(dict):
    """
    A document stored in the database.

    This class provides a way to access both a document's content and
    its ID using ``doc.doc_id``.
    """

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value)
        self.doc_id = doc_id

class Table:
    """
    Represents a single TinyDB table.

    It provides methods for accessing and manipulating documents.

    .. admonition:: Query Cache

        As an optimization, a query cache is implemented using a
        :class:`~tinydb.utils.LRUCache`. This class mimics the interface of
        a normal ``dict``, but starts to remove the least-recently used entries
        once a threshold is reached.

        The query cache is updated on every search operation. When writing
        data, the whole cache is discarded as the query results may have
        changed.

    .. admonition:: Customization

        For customization, the following class variables can be set:

        - ``document_class`` defines the class that is used to represent
          documents,
        - ``document_id_class`` defines the class that is used to represent
          document IDs,
        - ``query_cache_class`` defines the class that is used for the query
          cache
        - ``default_query_cache_capacity`` defines the default capacity of
          the query cache

        .. versionadded:: 4.0


    :param storage: The storage instance to use for this table
    :param name: The table name
    :param cache_size: Maximum capacity of query cache
    """
    document_class = Document
    document_id_class = int
    query_cache_class = LRUCache
    default_query_cache_capacity = 10

    def __init__(self, storage: Storage, name: str, cache_size: int=default_query_cache_capacity):
        """
        Create a table instance.
        """
        self._storage = storage
        self._name = name
        self._query_cache: LRUCache[QueryLike, List[Document]] = self.query_cache_class(capacity=cache_size)
        self._next_id = None

    def __repr__(self):
        args = ['name={!r}'.format(self.name), 'total={}'.format(len(self)), 'storage={}'.format(self._storage)]
        return '<{} {}>'.format(type(self).__name__, ', '.join(args))

    @property
    def name(self) -> str:
        """
        Get the table name.
        """
        return self._name

    @property
    def storage(self) -> Storage:
        """
        Get the table storage instance.
        """
        return self._storage

    def insert(self, document: Mapping) -> int:
        """
        Insert a new document into the table.

        :param document: the document to insert
        :returns: the inserted document's ID
        """
        doc_id = self._get_next_id()
        self._storage.write(self._name, {doc_id: document})
        self._query_cache.clear()
        return doc_id

    def insert_multiple(self, documents: Iterable[Mapping]) -> List[int]:
        """
        Insert multiple documents into the table.

        :param documents: an Iterable of documents to insert
        :returns: a list containing the inserted documents' IDs
        """
        doc_ids = []
        for document in documents:
            doc_ids.append(self.insert(document))
        return doc_ids

    def all(self) -> List[Document]:
        """
        Get all documents stored in the table.

        :returns: a list with all documents.
        """
        return [self.document_class(doc, doc_id) for doc_id, doc in self._read_table().items()]

    def search(self, cond: QueryLike) -> List[Document]:
        """
        Search for all documents matching a 'where' cond.

        :param cond: the condition to check against
        :returns: list of matching documents
        """
        if cond in self._query_cache:
            return self._query_cache[cond]
        
        docs = [doc for doc in self.all() if cond(doc)]
        self._query_cache[cond] = docs
        return docs

    def get(self, cond: Optional[QueryLike]=None, doc_id: Optional[int]=None, doc_ids: Optional[List]=None) -> Optional[Union[Document, List[Document]]]:
        """
        Get exactly one document specified by a query or a document ID.
        However, if multiple document IDs are given then returns all
        documents in a list.
        
        Returns ``None`` if the document doesn't exist.

        :param cond: the condition to check against
        :param doc_id: the document's ID
        :param doc_ids: the document's IDs(multiple)

        :returns: the document(s) or ``None``
        """
        if doc_id is not None:
            return self.document_class(self._read_table().get(doc_id, {}), doc_id) or None
        elif doc_ids is not None:
            return [self.document_class(self._read_table().get(id, {}), id) for id in doc_ids if id in self._read_table()]
        elif cond is not None:
            for doc in self.search(cond):
                return doc
        return None

    def contains(self, cond: Optional[QueryLike]=None, doc_id: Optional[int]=None) -> bool:
        """
        Check whether the database contains a document matching a query or
        an ID.

        If ``doc_id`` is set, it checks if the db contains the specified ID.

        :param cond: the condition use
        :param doc_id: the document ID to look for
        """
        if doc_id is not None:
            return doc_id in self._read_table()
        elif cond is not None:
            return len(self.search(cond)) > 0
        return False

    def update(self, fields: Union[Mapping, Callable[[Mapping], None]], cond: Optional[QueryLike]=None, doc_ids: Optional[Iterable[int]]=None) -> List[int]:
        """
        Update all matching documents to have a given set of fields.

        :param fields: the fields that the matching documents will have
                       or a method that will update the documents
        :param cond: which documents to update
        :param doc_ids: a list of document IDs
        :returns: a list containing the updated document's ID
        """
        updated = []
        if doc_ids is not None:
            for doc_id in doc_ids:
                if doc_id in self._read_table():
                    updated.append(doc_id)
                    self._update_document(doc_id, fields)
        else:
            for doc in self.search(cond):
                updated.append(doc.doc_id)
                self._update_document(doc.doc_id, fields)
        return updated

    def update_multiple(self, updates: Iterable[Tuple[Union[Mapping, Callable[[Mapping], None]], QueryLike]]) -> List[int]:
        """
        Update all matching documents to have a given set of fields.

        :returns: a list containing the updated document's ID
        """
        updated = []
        for fields, cond in updates:
            updated.extend(self.update(fields, cond))
        return updated

    def upsert(self, document: Mapping, cond: Optional[QueryLike]=None) -> List[int]:
        """
        Update documents, if they exist, insert them otherwise.

        Note: This will update *all* documents matching the query. Document
        argument can be a tinydb.table.Document object if you want to specify a
        doc_id.

        :param document: the document to insert or the fields to update
        :param cond: which document to look for, optional if you've passed a
        Document with a doc_id
        :returns: a list containing the updated documents' IDs
        """
        if isinstance(document, Document):
            doc_id = document.doc_id
            document = dict(document)
            if doc_id is not None:
                if self.contains(doc_id=doc_id):
                    self.update(document, doc_ids=[doc_id])
                    return [doc_id]
                else:
                    return [self.insert(document)]
        
        updated = self.update(document, cond)
        if updated:
            return updated
        return [self.insert(document)]

    def remove(self, cond: Optional[QueryLike]=None, doc_ids: Optional[Iterable[int]]=None) -> List[int]:
        """
        Remove all matching documents.

        :param cond: the condition to check against
        :param doc_ids: a list of document IDs
        :returns: a list containing the removed documents' ID
        """
        removed = []
        if doc_ids is not None:
            for doc_id in doc_ids:
                if doc_id in self._read_table():
                    removed.append(doc_id)
                    del self._read_table()[doc_id]
        elif cond is not None:
            for doc in self.search(cond):
                removed.append(doc.doc_id)
                del self._read_table()[doc.doc_id]
        self._write_table(self._read_table())
        return removed

    def truncate(self) -> None:
        """
        Truncate the table by removing all documents.
        """
        self._write_table({})
        self._query_cache.clear()

    def count(self, cond: QueryLike) -> int:
        """
        Count the documents matching a query.

        :param cond: the condition use
        """
        return len(self.search(cond))

    def clear_cache(self) -> None:
        """
        Clear the query cache.
        """
        self._query_cache.clear()

    def __len__(self):
        """
        Count the total number of documents in this table.
        """
        return len(self._read_table())

    def __iter__(self) -> Iterator[Document]:
        """
        Iterate over all documents stored in the table.

        :returns: an iterator over all documents.
        """
        for doc_id, doc in self._read_table().items():
            yield self.document_class(doc, self.document_id_class(doc_id))

    def _get_next_id(self):
        """
        Return the ID for a newly inserted document.
        """
        if self._next_id is None:
            self._next_id = max(self._read_table().keys() or [0]) + 1
        else:
            self._next_id += 1
        return self._next_id

    def _read_table(self) -> Dict[str, Mapping]:
        """
        Read the table data from the underlying storage.

        Documents and doc_ids are NOT yet transformed, as 
        we may not want to convert *all* documents when returning
        only one document for example.
        """
        return self._storage.read().get(self._name, {})

    def _update_table(self, updater: Callable[[Dict[int, Mapping]], None]):
        """
        Perform a table update operation.

        The storage interface used by TinyDB only allows to read/write the
        complete database data, but not modifying only portions of it. Thus,
        to only update portions of the table data, we first perform a read
        operation, perform the update on the table data and then write
        the updated data back to the storage.

        As a further optimization, we don't convert the documents into the
        document class, as the table data will *not* be returned to the user.
        """
        data = self._storage.read()
        data[self._name] = self._read_table()
        updater(data[self._name])
        self._storage.write(data)
        self._query_cache.clear()
