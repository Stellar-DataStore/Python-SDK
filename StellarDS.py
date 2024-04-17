import os
import json
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

#PIP library
import requests
from cryptography.fernet import Fernet

KEY = b'XUvD2UJexw2RKw_2QzN48LT4FFNJ0QDY6fyRRu9-3hU='

class AuthorizationHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        if 'code' in query_params:
            self.server.auth_code = query_params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html_content = """
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Authorization successful</title>
                    <style>
                        body {
                            font-family: Arial, sans-serif;
                            background-color: #f4f4f4;
                            text-align: center;
                        }
                        .container {
                            margin-top: 100px;
                        }
                        h1 {
                            color: #333;
                        }
                        p {
                            color: #666;
                        }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Authorization successful!</h1>
                        <p>You can close this tab now.</p>
                    </div>
                </body>
                </html>
            """
            self.wfile.write(html_content.encode('utf-8'))
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html_content = """
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Bad Request</title>
                    <style>
                        body {
                            font-family: Arial, sans-serif;
                            background-color: #f4f4f4;
                            text-align: center;
                        }
                        .container {
                            margin-top: 100px;
                        }
                        h1 {
                            color: #ff0000;
                        }
                        p {
                            color: #666;
                        }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Bad Request</h1>
                        <p>Missing code.</p>
                    </div>
                </body>
                </html>
            """
            self.wfile.write(html_content.encode('utf-8'))

def _process_response(response, response_class):
    if response_class is not BlobResponse:
        #rint("\n", response.text)
        json_data = response.json() if response.status_code != 401 else {}
    else:
        #print("\n", response.content)
        json_data = {"data": {"bytes": response.content}} if response.status_code == 200 else response.json()
    return response_class(
        data=json_data.get("data", {}),
        messages=json_data.get("messages", []),
        isSuccess=json_data.get("isSuccess"),
        statusCode=response.status_code
    )

def _get_fernet():
    return Fernet(KEY)

def _encrypt_text(text):
    fernet = _get_fernet()
    return fernet.encrypt(text.encode()).decode()

def _decrypt_text(encrypted_text):
    fernet = _get_fernet()
    return fernet.decrypt(encrypted_text.encode()).decode()

def _save_settings(settings, is_persistent, force_save):
    if is_persistent or force_save:
        fernet = _get_fernet()
        encrypted_settings = {}
        for key, value in settings.items():
            if key in ["REFRESH_TOKEN", "ACCESS_TOKEN"]:
                encrypted_settings[key] = _encrypt_text(value)
            else:
                encrypted_settings[key] = value
        with open("settings.json", "w") as settings_file:
            json.dump(encrypted_settings, settings_file)

def _load_settings():
    fernet = _get_fernet()
    try:
        with open("settings.json", "r") as settings_file:
            if os.path.getsize("settings.json") == 0:
                return {}
            encrypted_settings = json.load(settings_file)
            decrypted_settings = {}
            for key, value in encrypted_settings.items():
                if key in ["REFRESH_TOKEN", "ACCESS_TOKEN"]:
                    decrypted_settings[key] = _decrypt_text(value)
                else:
                    decrypted_settings[key] = value
            return decrypted_settings
    except FileNotFoundError:
        return {}

class StellarDS():
    BASE_URL = "https://api.stellards.io/v1"

    def __init__(self, is_oauth=False, is_persistent=True):
        self.project = self.Project(self)
        self.projecttier = self.ProjectTier(self)
        self.table = self.Table(self)
        self.field = self.Field(self)
        self.data = self.Data(self)
        self.user = self.User(self)
        self.is_oauth = is_oauth
        self.is_persistent = is_persistent
        settings = self._load_settings()
        self.EXPIRE_TIME = settings[0]
        self.REFRESH_TOKEN = settings[1]
        self.ACCESS_TOKEN = settings[2]
        self._on_access_token_callback = None
        self._on_request_start_callback = None
        self._on_request_done_callback = None

    def _load_settings(self):
        settings = _load_settings()
        return settings.get("EXPIRE_TIME", None), settings.get("REFRESH_TOKEN", None), settings.get("ACCESS_TOKEN", None)

    def on_access_token(self, callback):
        self._on_access_token_callback = callback
        
    def on_request_start(self, callback):
        self._on_request_start_callback = callback
        
    def on_request_done(self, callback):
        self._on_request_done_callback = callback

    def _check_access_token(self):
        if self.is_oauth:
            expire_time = float(self.EXPIRE_TIME) if self.EXPIRE_TIME is not None else None
            if expire_time is not None and expire_time <= time.time():
                self._refresh()

    def _refresh(self):
        url = f"{self.BASE_URL}/oauth/token"
        headers = {
            "accept": "text/plain",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "refresh_token",
            "client_id": self.CLIENT_ID,
            "client_secret": self.CLIENT_SECRET,
            "refresh_token": self.REFRESH_TOKEN
        }
        response = requests.post(url, headers=headers, data=data)
        if self._on_access_token_callback and response.status_code==200:
            self._on_access_token_callback()
        self._update_tokens(response.json())

    def _update_tokens(self, response_json):
        settings = {
            "REFRESH_TOKEN": response_json.get('refresh_token'),
            "ACCESS_TOKEN": response_json.get('access_token'),
            "EXPIRE_TIME": time.time() + response_json.get('expires_in')
        }
        self.EXPIRE_TIME = settings["EXPIRE_TIME"]
        self.REFRESH_TOKEN = settings["REFRESH_TOKEN"]
        self.ACCESS_TOKEN = settings["ACCESS_TOKEN"]
        _save_settings(settings, self.is_persistent, force_save=False)

    def access_token(self, access_token):
        if not self.is_oauth:
            self.ACCESS_TOKEN = access_token
            if self._on_access_token_callback:
                self._on_access_token_callback()

    def ping(self):
        self._check_access_token()
        if self._on_request_start_callback:
            self._on_request_start_callback()
        endpoint = "ping"
        url = f"{self.BASE_URL}/{endpoint}"
        headers = {"Authorization": f"Bearer {self.ACCESS_TOKEN}"}
        response = requests.get(url, headers=headers).text
        if self._on_request_done_callback:
            self._on_request_done_callback()
        return response

    def oauth(self, client_id, redirect_uri, client_secret):
        if self.is_oauth:
            self.CLIENT_ID = client_id
            self.CLIENT_SECRET = client_secret
            if self.EXPIRE_TIME is None or float(self.EXPIRE_TIME) <= time.time():
                self._authorize(client_id, redirect_uri, client_secret)

    def _authorize(self, client_id, redirect_uri, client_secret):
        url = f"https://stellards.io/oauth?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}"
        webbrowser.open(url)
        server_address = ('', 8080)
        httpd = HTTPServer(server_address, AuthorizationHandler)
        httpd.handle_request()
        token = httpd.auth_code
        self._exchange_code_for_token(client_id, client_secret, token, redirect_uri)

    def _exchange_code_for_token(self, client_id, client_secret, code, redirect_uri):
        url = f"{self.BASE_URL}/oauth/token"
        headers = {
            "accept": "text/plain",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri
        }
        response = requests.post(url, headers=headers, data=data)
        if self._on_access_token_callback and response.status_code==200:
            self._on_access_token_callback()
        self._update_tokens(response.json())
        
    def clear_tokens(self):
        with open("settings.json", "w") as settings_file:
            pass
            
    def load_tokens(self):
        _load_settings()
        
    def save_tokens(self):
        settings = {
            "REFRESH_TOKEN": self.REFRESH_TOKEN,
            "ACCESS_TOKEN": self.ACCESS_TOKEN,
            "EXPIRE_TIME": self.EXPIRE_TIME
        }
        _save_settings(settings, self.is_persistent, force_save=True)

    class Project:
        ENDPOINT = "schema/project"

        def __init__(self, parent):
            self.parent = parent

        def _request(self, method, project=None, data=None):
            self.parent._check_access_token()
            if self.parent._on_request_start_callback:
                self.parent._on_request_start_callback()
            url = f"{self.parent.BASE_URL}/{self.ENDPOINT}"
            headers = {
                "accept": "text/plain",
                "Authorization": f"Bearer {self.parent.ACCESS_TOKEN}"
            }
            params = {"project": str(project)} if project is not None else None
            response = method(url, headers=headers, params=params, json=data)
            if self.parent._on_request_done_callback:
                self.parent._on_request_done_callback()
            return _process_response(response, ProjectResponse)

        def get(self, project=None):
            return self._request(requests.get, project)

        def update(self, project, data):
            return self._request(requests.put, project, {
                "name": data.name,
                "description": data.description,
                "isMultitenant": data.is_multitenant
            })

    class ProjectTier:
        ENDPOINT = "project-tier"

        def __init__(self, parent):
            self.parent = parent
            self.current = self.Current(self)

        def _request(self, method, project=None):
            self.parent._check_access_token()
            if self.parent._on_request_start_callback:
                self.parent._on_request_start_callback()
            url = f"{self.parent.BASE_URL}/{self.ENDPOINT}"
            headers = {
                "accept": "text/plain",
                "Authorization": f"Bearer {self.parent.ACCESS_TOKEN}"}
            params = {"project": str(project)} if project else {}
            response = method(url, headers=headers, params=params)
            if self.parent._on_request_done_callback:
                self.parent._on_request_done_callback()
            return _process_response(response, ProjectTierResponse)
            
        def get(self, project=None):
            return self._request(requests.get, project)

        class Current:
            ENDPOINT = "project-tier/current"

            def __init__(self, parent):
                self.parent = parent

            def _request(self, method, project):
                self.parent.parent._check_access_token()
                if self.parent.parent._on_request_start_callback:
                    self.parent.parent._on_request_start_callback()
                url = f"{self.parent.parent.BASE_URL}/{self.ENDPOINT}"
                headers = {
                    "accept": "text/plain",
                    "Authorization": f"Bearer {self.parent.parent.ACCESS_TOKEN}"
                }
                params = {"project": str(project)}
                response = method(url, headers=headers, params=params)
                if self.parent.parent._on_request_done_callback:
                    self.parent.parent._on_request_done_callback()
                return _process_response(response, ProjectTierResponse)

            def get(self, project):
                return self._request(requests.get, project)

    class Table:
        ENDPOINT = "schema/table"

        def __init__(self, parent):
            self.parent = parent

        def _request(self, method, project, table=None, data=None):
            self.parent._check_access_token()
            if self.parent._on_request_start_callback:
                self.parent._on_request_start_callback()
            url = f"{self.parent.BASE_URL}/{self.ENDPOINT}"
            headers = {
                "accept": "text/plain",
                "Authorization": f"Bearer {self.parent.ACCESS_TOKEN}"
            }
            params = {"project": str(project), "table": table} if table is not None else {"project": str(project)}
            response = method(url, headers=headers, params=params, json=data)
            if self.parent._on_request_done_callback:
                self.parent._on_request_done_callback()
            return _process_response(response, TableResponse)

        def get(self, project, table=None):
            return self._request(requests.get, project, table)

        def update(self, project, table, data):
            return self._request(requests.put, project, table, {
                "name": data.name,
                "description": data.description,
                "isMultitenant": data.is_multitenant
            })

        def add(self, project, data):
            return self._request(requests.post, project, None, {
                "name": data.name,
                "description": data.description,
                "isMultitenant": data.is_multitenant
            })

        def delete(self, project, table):
            return self._request(requests.delete, project, table)

    class Field:
        ENDPOINT = "schema/table/field"

        def __init__(self, parent):
            self.parent = parent

        def _request(self, method, project, table, field=None, data=None):
            self.parent._check_access_token()
            if self.parent._on_request_start_callback:
                self.parent._on_request_start_callback()
            url = f"{self.parent.BASE_URL}/{self.ENDPOINT}"
            headers = {
                "accept": "text/plain",
                "Authorization": f"Bearer {self.parent.ACCESS_TOKEN}"
            }
            params = {"project": str(project), "table": table, "field": field} if field is not None else {"project": str(project), "table": table}
            response = method(url, headers=headers, params=params, json=data)
            if self.parent._on_request_done_callback:
                self.parent._on_request_done_callback()
            return _process_response(response, FieldResponse)

        def get(self, project, table, field=None):
            return self._request(requests.get, project, table, field)

        def update(self, project, table, field, data):
            return self._request(requests.put, project, table, field, {
                "name": data.name,
                "type": data.type
            })

        def add(self, project, table, data):
            return self._request(requests.post, project, table, None, {
                "name": data.name,
                "type": data.type
            })

        def delete(self, project, table, field):
            return self._request(requests.delete, project, table, field)

    class Data:
        ENDPOINT = "data/table"
        
        def __init__(self, parent):
            self.parent = parent
            self.blob = self.Blob(self)
            
        def _request(self, method, project, table, record=None, queries=None, data=None, force=None, delete_type=None):
            self.parent._check_access_token()
            if self.parent._on_request_start_callback:
                self.parent._on_request_start_callback()
            if delete_type == 'list':
                url = f"{self.parent.BASE_URL}/{self.ENDPOINT}/delete"
            elif delete_type == 'full':
                url = f"{self.parent.BASE_URL}/{self.ENDPOINT}/clear"
            else:
                url = f"{self.parent.BASE_URL}/{self.ENDPOINT}"
            headers = {
                "accept": "text/plain",
                "Authorization": f"Bearer {self.parent.ACCESS_TOKEN}"
            }
            params = {"project": str(project), "table": table}
            if record is not None:
                params["record"] = record
            if force is not None:
                params["force"] = force
            if queries is not None:
                data_queries = {
                    "Offset": queries.Offset,
                    "Take": queries.Take,
                    "JoinQuery": queries.JoinQuery,
                    "WhereQuery": queries.WhereQuery,
                    "SortQuery": queries.SortQuery
                }
                params.update(data_queries)
            response = method(url, headers=headers, params=params, json=data)
            if self.parent._on_request_done_callback:
                self.parent._on_request_done_callback()
            return _process_response(response, DataResponse)
        
        def get(self, project, table, queries=None):
            return self._request(requests.get, project, table, None, queries)
        
        def update(self, project, table, record, record_list=None, force=None):
            record_data = {key: getattr(record, key) for key in record.__dict__.keys()}
            if record_list is not None:
                data = {"idList": [str(value) for value in record_list.id], "record": record_data}
            else:
                data = {"record": record_data}
            return self._request(requests.put, project, table, None, None, data, force)

        def add(self, project, table, data):
            return self._request(requests.post, project, table, None, None, {
                "records":[{key: getattr(data, key) for key in data.__dict__.keys()}]
            })
        
        def delete(self, project, table, record_list):
            data = [str(item) for item in record_list.id]
            if len(data) == 1:
                return self._request(requests.delete, project, table, data)
            else:
                return self._request(requests.post, project, table, None, None, data, None, 'list')
                
        def clear(self, project, table):
            return self._request(requests.delete, project, table, None, None, None, None, 'full')

        class Blob:
            ENDPOINT = "data/table/blob"

            def __init__(self, parent):
                self.parent = parent

            def _request(self, method, project, table, record, field, data=None):
                self.parent.parent._check_access_token()
                if self.parent.parent._on_request_start_callback:
                    self.parent.parent._on_request_start_callback()
                url = f"{self.parent.parent.BASE_URL}/{self.ENDPOINT}"
                headers = {
                    "accept": "text/plain",
                    "Authorization": f"Bearer {self.parent.parent.ACCESS_TOKEN}"
                }
                params = {"project": str(project), "table": table, "record": record, "field": field}
                data = {'data': data} if data is not None else None
                response = method(url, headers=headers, params=params, files=data)
                if self.parent.parent._on_request_done_callback:
                    self.parent.parent._on_request_done_callback()
                return _process_response(response, BlobResponse)

            def get(self, project, table, record, field):
                return self._request(requests.get, project, table, record, field, None)

            def add(self, project, table, record, field, data):
                return self._request(requests.post, project, table, record, field, data)
                
    class User:
        ENDPOINT = "user"

        def __init__(self, parent):
            self.parent = parent

        def _request(self, method, data):
            self.parent._check_access_token()
            if self.parent._on_request_start_callback:
                self.parent._on_request_start_callback()
            url = f"{self.parent.BASE_URL}/{self.ENDPOINT}"
            headers = {
                "accept": "text/plain",
                "Authorization": f"Bearer {self.parent.ACCESS_TOKEN}"
            }
            response = method(url, headers=headers, json=data)
            if self.parent._on_request_done_callback:
                self.parent._on_request_done_callback()
            return _process_response(response, UserResponse)

        def get(self):
            return self._request(requests.get, None)

        def update(self, data):
            return self._request(requests.put, {
                "username": data.username,
                "email": data.email,
                "emailCallbackUrl": data.email_callback_url,
                "password": data.password
            })

        def delete(self):
            return self._request(requests.delete, None)

class BaseResponse:
    def __init__(self, data, messages, isSuccess=None, statusCode=None):
        if isinstance(data, list):
            self.data = [self.Data(**field) for field in data]
        elif isinstance(data, dict):
            self.data = self.Data(**data)
        self.messages = [self.Messages(**msg) for msg in messages]
        self.is_success = isSuccess
        self.status_code = statusCode

    class Data:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    class Messages:
        def __init__(self, **messages):
            for key, value in messages.items():
                setattr(self, key, value)

class ProjectResponse(BaseResponse):
    class Data(BaseResponse.Data):
        def __init__(self, id=None, name=None, description=None, isMultitenant=None):
            super().__init__(id=id, name=name, description=description, is_multitenant=isMultitenant)

class ProjectTierResponse(BaseResponse):
    class Data(BaseResponse.Data):
        def __init__(self, name=None, users=None, tables=None, maxRequests=None):
            super().__init__(name=name, users=users, tables=tables, max_requests=maxRequests)

class TableResponse(BaseResponse):
    class Data(BaseResponse.Data):
        def __init__(self, id=None, name=None, description=None, isMultitenant=None):
            super().__init__(id=id, name=name, description=description, is_multitenant=isMultitenant)

class FieldResponse(BaseResponse):
    class Data(BaseResponse.Data):
        def __init__(self, id=None, name=None, type=None):
            super().__init__(id=id, name=name, type=type)

class DataResponse(BaseResponse):
    class Data(BaseResponse.Data):
        def __init__(self, id=None, **extra):
            super().__init__(id=id, **extra)
            
class BlobResponse(BaseResponse):
    class Data(BaseResponse.Data):
        def __init__(self, bytes=None):
            super().__init__(bytes=bytes)
            
class UserResponse(BaseResponse):
    class Data(BaseResponse.Data):
        def __init__(self, username=None, email=None):
            super().__init__(username=username, email=email)

class Project:
    def __init__(self, name, description, is_multitenant):
        self.name, self.description, self.is_multitenant = name, description, is_multitenant

class Table:
    def __init__(self, name, description, is_multitenant):
        self.name, self.description, self.is_multitenant = name, description, is_multitenant

class Field:
    def __init__(self, name, type):
        self.name, self.type = name, type

class DataQueries:
    def __init__(self, Offset=None, Take=None, JoinQuery=None, WhereQuery=None, SortQuery=None):
        self.Offset, self.Take, self.JoinQuery, self.WhereQuery, self.SortQuery = Offset, Take, JoinQuery, WhereQuery, SortQuery

class RecordList:
	def __init__(self, id):
		self.id = id

class User:
    def __init__(self, username=None, email=None, emailCallbackUrl=None, password=None):
        self.username, self.email, self.email_callback_url, self.password = username, email, emailCallbackUrl, password
