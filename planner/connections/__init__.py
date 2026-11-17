"""Device-to-device connections, derived from the data the other modules hold.

PR 2a is read-only: ``matchers`` finds what the stored text implies,
``graph`` turns that and the existing foreign keys into one project graph, and
the ``infer_connections`` command reports on the same matches. Nothing here
writes. A stored Connection model (and its confirm UI) is PR 2b.
"""
