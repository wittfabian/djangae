# djangae.contrib.search

This is a minimal search engine built on the Google Cloud Datastore
that in part mimics the old Google App Engine Search API.

It exists for two reasons:

1. An upgrade path from the GAE Search API.
2. To aid smaller projects that don't need to run their own ElasticSearch instance.


# Query Format

The original App Engine Search query format was pretty tricky to parse, and not often used
extensively. The query format used in djangae.contrib.search is much simpler.

## OR operator

You can create a multiple branch search with the OR operator. ORs are not nested, you can simply
use:

```
marathon OR race OR run
```

The OR can be lower case, as 'or' is a common word that is not indexed

## Exact match

You can combine words together to return documents that have an exact match by using quotes. e.g.

```
"tallest building"
```

This can in turn be used with the OR operator:

```
"tallest building" OR tower
```

## Field match

Finally, you can use the `:` operator to specify a Document field to search:

```
name:james
```

To combine with the OR operator you'll need to duplicate the `:` operator:

```
name:james OR name:jim OR last_name:kirk
```

You can also combine with exact matching:

```
name:"james kirk" OR name:spock
```

# Field Types

The App Engine Search API had an array of field types. Currently djangae.contrib.search only
supports the following:

 - TextField - A blob of text up to 1024 ** 2 chars in length
 - AtomField - A text field that is up to 1000 chars in length
 - DateField - A field for storing a Python datetime or date field.
 - NumberField - A field for storing an integer

AtomFields are only matched on exact matches.
