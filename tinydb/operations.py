"""
A collection of update operations for TinyDB.

They are used for updates like this:

>>> db.update(delete('foo'), where('foo') == 2)

This would delete the ``foo`` field from all documents where ``foo`` equals 2.
"""

def delete(field):
    """
    Delete a given field from the document.
    """
    pass

def add(field, n):
    """
    Add ``n`` to a given field in the document.
    """
    def transform(doc):
        if field in doc:
            doc[field] += n
        return doc
    return transform

def subtract(field, n):
    """
    Subtract ``n`` from a given field in the document.
    """
    def transform(doc):
        if field in doc:
            doc[field] -= n
        return doc
    return transform

def set(field, val):
    """
    Set a given field to ``val``.
    """
    def transform(doc):
        doc[field] = val
        return doc
    return transform

def increment(field):
    """
    Increment a given field in the document by 1.
    """
    return add(field, 1)

def decrement(field):
    """
    Decrement a given field in the document by 1.
    """
    return subtract(field, 1)
