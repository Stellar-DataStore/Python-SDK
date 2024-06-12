# StellarDS Python SDK
## Introduction

In the world of Python development, efficient database integration is crucial for building applications. We present the free StellarDS.io Python library to simplify database interactions. For developers looking to get started, you can easily access this on [PyPI](https://pypi.org/project/StellarDS/) or on our [Github](https://github.com/Stellar-DataStore/Python-SDK) repository, which includes a demo to help you get started with StellarDS.io.

## Create a Python Application
### Setup

1. Navigate to [StellarDS.io](https://stellards.io) and sign up for Stellar Datastore if not already done.
2. Go to Managa Database from the navigation bar.
3. Under Applications select to get access to your database via OAuth or via access tokens.
    1. When choosing OAuth, set a befitting name and set up the CallbackUrl as follows [http://localhost:8080](http://localhost:8080). Choose the required role for people to determine the access rights the application should have. Be sure to keep the `client_secret` and `client_id` for later.
    2. When choosing Access Tokens, set a befitting name and set up the duration of validity of the access token. Choose the required role for people to determine the access rights the application should have. Leave the domain empty.
4. In your Python environment execute the following command:
    ```console
    pip install stellards requests cryptography
    ```
### Initializing the SDK

To start using the StellarDS.io SDK you should first import the StellarDS class and create an instance of this class. When creating the instance you've got the option to either use OAuth or Access Token. And an option to save your tokens in a seperate file, so authenthication isn't required every time you start the script.

```python
from StellarDS import StellarDS

stellar_ds = StellarDS(is_oauth=False, is_persistent=False)
```

When setting the boolean `is_oauth` to True, we should start the OAuth-flow with the required parameters.

```python
stellar_ds.oauth('your_client_id', 'http://localhost:8080', 'your_client_secret')
```

When setting the boolean `is_oauth` to False, we can start using the SDK after an `access_token` was provided.

```python
stellar_ds.access_token('your_access_token')
```

When setting the boolean `is_persistent` to True, when logging in a new file will be created with your encrypted tokens. This is so you don't have to keep logging in when restarting your application.

### Test Connection

To check if everything is setup correctly you could use the `ping()` function.

```python
stellar_ds.ping()
```

### Project

When working with projects, it's recommended to import the `Project` class, since it can be used in some methods. 

```python
from StellarDS import Project
```

To get information on a specific project, you could use:

```python
stellar_ds.project.get('project_id')
```

Or leave it empty to get the projects which you are a part of:

```python
stellar_ds.project.get()
```

To update a project, you can use the built-in `Project` class.

```python
project_data = Project('name', 'description', True)
stellar_ds.project.update('project_id', project_data)
```

Each call you make wil return a `Project Response` class which contains the following information:

* data
    * id
    * name
    * description
    * is_multitenant
* messages
    * code
    * message
    * type
* is_succes
* status_code

For example, if you want to get the `name` of one of your projects:

```python
stellar_ds.project.get().data[0].name
```

### Table

When working with tables it's recommended to import the `Table` class,
since it can be used in some methods. 

```python
from StellarDS import Table
```

To get information on a specific table you could use:

```python
stellar_ds.project.get('project_id', 'table_id')
```

You can also get all your tables.

```python
stellar_ds.project.get('project_id')
```

To update an existing project you can use the built-in `Table` class.

```python
table_data = Table('name', 'description', True)
stellar_ds.table.update('project_id', 'table_id' table_data)
```

It's also possible to add a table in the following way:

```python
table_data = Table('name', 'description', True)
stellar_ds.table.add('project_id', table_data)
```

And deleting a table can be done as follows:

```python
stellar_ds.table.delete('project_id', 'table_id')
```

Each call you make wil return a `Table Response` class which contains the following information:

* data
    * id
    * name
    * description
    * is_multitenant
* messages
    * code
    * message
    * type
* is_succes
* status_code

So for example, if you want to get the `name` of a specific table:

```python
stellar_ds.table.get('project_id', 'table_id').data.name
```

### Field

When working with fields it's recommended to import the `Field` class,
since it can be used in some methods. 

```python
from StellarDS import Field
```

To get information on a specific field you could use:

```python
stellar_ds.field.get('project_id', 'table_id', 'field_id')
```

You can also get all your fields from a specific table.

```python
stellar_ds.field.get('project_id', 'table_id')
```

To update an existing project, you can use the build in `Field` class.

```python
field_data = Field('name', 'type')
stellar_ds.field.update('project_id', 'table_id', 'field_id', field_data)
```

It's also possible to add a field to a table in the following way:

```python
field_data = Field('name', 'type')
stellar_ds.field.add('project_id', 'table_id', field_data)
```

And deleting a field can be done as followed:

```python
stellar_ds.field.delete('project_id', 'table_id', 'field_id')
```

When updating or adding a field, it's possible to specify a datatype. Here are all the possible types that can be used:

* BigInt
* Boolean
* Blob
* DateTime
* Float
* Int
* NvarChar(255)
* Real
* SmallInt
* TinyInt

Each call you make wil return a `Field Response` class which contains the following information:

* data
    * id
    * name
    * type
* messages
    * code
    * message
    * type
* is_succes
* status_code

As example, if you want to get the `status_code` of your request:

```python
stellar_ds.field.get('project_id', 'table_id', 'field_id').status_code
```

### Data

When working with data it's recommended to import the `DataQueries` and `RecordList` classes, since it can be used in some methods. 

```python
from StellarDS import DataQueries, RecordList
```

To get information on data in a table, you could use:

```python
stellar_ds.data.get('project_id', 'table_id')
```

It's possible to add an extra parameter with different queries by using the `DataQueries` class.

* Offset

```python
queries = DataQueries(Offset='number')
stellar_ds.data.get('project_id', 'table_id', queries)
```

* Take

```python
queries = DataQueries(Take='number')
stellar_ds.data.get('project_id', 'table_id', queries)
```

* JoinQuery

```python
queries = DataQueries(JoinQuery='table1;field1=table2;field2')
stellar_ds.data.get('project_id', 'table_id', queries)
```

* WhereQuery

```python
queries = DataQueries(WhereQuery='field1;condition1;value1&field2;condition2;value2')
stellar_ds.data.get('project_id', 'table_id', queries)
```

* SortQuery

```python
queries = DataQueries(SortQuery='field1;asc|desc&Field2;asc|desc')
stellar_ds.data.get('project_id', 'table_id', queries)
```

To update existing data, you can use the build in `RecordList` class to specify which data you want to change. The method also requires a class with your data you wish to change.

```python
class Record:
    def __init__(self, field1 , field2):
        self.field1, self.field2 = field1, field2
```

```python
record = Record('field1', 'field2')
recordList = RecordList(['record_id1', 'record_id2'])
stellar_ds.data.update('project_id', 'table_id', record, recordList, True)
```

It's also possible to add data in the following way:

```python
record = Record('field1', 'field2')
stellar_ds.data.add('project_id', 'table_id', record)
```

And deleting data can be done as follows:

```python
recordList = RecordList(['record_id1'])
stellar_ds.data.delete('project_id', 'table_id', recordList)
```

You could also immediately clear the full table.

```python
data_clear_response = stellar_ds.data.clear('project_id', 'table_id')

```

When working with a `Blob` things are a little bit different. To fetch blob data, you could use:

```python
stellar_ds.data.blob.get('project_id', 'table_id', 'record_id', 'field_name')
```

And adding would be done like follows:

```python
data = 'record_bytes'
stellar_ds.data.blob.add('project_id', 'table_id', 'record_id', 'field_name', data)
```

Each normal call you make wil return a `Data Response` class which contains the following information:

* data
    * field1
    * field2
    * field3
* messages
    * code
    * message
    * type
* is_succes
* status_code

When making a call for a `Blob` you will get a `Blob Response` class with this information:

* data
    * bytes
* messages
    * code
    * message
    * type
* is_succes
* status_code

For example, if you want to get the `bytes` from a `blob` of your request:

```python
stellar_ds.data.blob.get('project_id', 'table_id', 'record_id', 'field_name').data.bytes
```

### User

When working with users, it's recommended to import the `User` class,
since it can be used in some methods. 

```python
from StellarDS import User
```

To get information on the `user`, you could use:

```python
stellar_ds.user.get()
```

To update the current user, you can use the build in `User` class.

```python
user = User(username='username', email='email')
stellar_ds.user.update(user)
```

Each call you make wil return a `User Response` class which contains the following information:

* data
    * username
    * email
* messages
    * code
    * message
    * type
* is_succes
* status_code

For instance, if you want to get the `email` of your user:

```python
stellar_ds.user.get().data.email
```

### Project Tier

To get information on the `Project Tier` you could use:

```python
stellar_ds.projecttier.get('project_id')

```

To get the current used `Project Tier` statistics, you can use:

```python
stellar_ds.projecttier.current.get('project_id')
```

Each call you make wil return a `Project Tier Response` class which contains the following information:

* data
    * name
    * users
    * tables
    * max_requests
* messages
    * code
    * message
    * type
* is_succes
* status_code

So if you want to get the current tables used in your `Project Tier`:

```python
stellar_ds.projecttier.current.get('project_id').data.tables
```

### Events

If you want to get notified when you got a new `access_token`, you could use:

```python
stellar_ds.on_access_token('function')
```

If you want to get notified when a request is started, you could use:

```python
stellar_ds.on_request_start('function')
```

If you want to get notified when a request is finished`, you could use:

```python
stellar_ds.on_request_done('function')
```

So for example if you want to `print()` something when a request is finished:

```python
def request_finished():
    print("text")

stellar_ds.on_request_done(request_finished)
```