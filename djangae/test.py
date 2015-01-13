import contextlib

@contextlib.contextmanager
def inconsistent_db(probability=0, connection='default'):
    from django.db import connections

    conn = connections[connection]

    if not hasattr(conn.creation, "testbed") or "datastore_v3" not in conn.creation.testbed._enabled_stubs:
        raise RuntimeError("Tried to use the inconsistent_db stub when not testing")

    from google.appengine.api import apiproxy_stub_map
    from google.appengine.datastore import datastore_stub_util

    stub = apiproxy_stub_map.apiproxy.GetStub('datastore_v3')

    # Set the probability of the datastore stub
    stub.SetConsistencyPolicy(datastore_stub_util.PseudoRandomHRConsistencyPolicy(probability=probability))

    yield

    # Restore to consistent mode
    stub.SetConsistencyPolicy(datastore_stub_util.PseudoRandomHRConsistencyPolicy(probability=1))
