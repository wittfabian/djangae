
# Cloud Spanner Backend

This is a work-in-progress implementation of a Django backend for Google's Cloud Spanner
database. 

## Implementation

Unfortunately, the Spanner client libraries don't work on the standard App Engine runtime. The only way to interact
with Cloud Spanner from GAE is to use the REST API. To abstract this a little, and to make implementing a Django backend
more like the other backends, I've implemented a stub DB API 2.0 connector in the "impl" folder. Theoretically it wouldn't
take much to separate this out into its own project, however at the moment it is tied to GAE due to the authentication mechanism.

The REST API works with the concept of a "session" which you use to submit all queries. I originally tied session to the 
`cursor` implementation - so that each new cursor created a new session. However, because transactions are tied to a session
and in the DB API expects transaction management to happen on the `connection` I've moved session management so that cursors
which share a connection also share a session.

A minor annoyance is that Spanner seems to use separate endpoints for queries which affect schema (e.g. CREATE TABLE) and those which manipulate rows (e.g. SELECT, UPDATE etc.) for this reason the DB API connector has to try to determine what
kind of query is being run. There are 3 types of query: DDL, READ and WRITE.

The separation between READ (SELECT) and WRITE (everything else) queries is necessary because Spanner has two different types
of transaction; `readOnly` and `readWrite`. It's costly to use a `readWrite` transaction when it's not necessary so the connector
only enables a `readWrite` transaction if it detects that the SQL is trying to manipulate data or if autocommit is disabled, 
in which case we have to assume that subsequent queries may require writing so we use `readWrite`

Autocommit is implemented in the connector by doing the following; if there is no active transaction when a query is run and new transaction is created by specifying `"transaction": {"begin": {}}` in the submitted POST data. This starts a new transaction, and returns the transactionId with the resultset. If autocommit is enabled, this transactionId is immediately committed otherwise the transactionId is stored.

## TODO

The following items are some of the things left to do, unfortunately we are blocked until we can work out why 
DDL queries (for changing schema) are not having any effect.

 - Implement session closing on the connection
 - Implement transaction rollback
 - Check through database features and configure the flags (DatabaseFeatures.X) appropriately
 - Implement returning fetched rows
 - Implement cursor description functions (queries return metadata which describes the fetched columns)
 - Query batching using the stream SQL API
 - fetchone, fetchmany etc.
