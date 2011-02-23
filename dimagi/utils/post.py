from __future__ import absolute_import
import os
from urlparse import urlparse
import httplib
import subprocess
import tempfile
from subprocess import PIPE
from restkit import Resource, BasicAuth

def post_authenticated_data(data, url, username, password):
    """
    Post basic authenticated data, using restkit
    """ 
    auth = BasicAuth(username, password)
    r = Resource(url, filters=[auth, ])
    return (r.post(payload=data).body_string(), None)
    
def post_authenticated_file(filename, url, username, password):
    """
    Post basic authenticated file, using restkit
    """ 
    file = open(filename, "rb")
    try:
        return post_authenticated_data(file.read(), url, username, password)
    finally:
        file.close()
    
def tmpfile(*args, **kwargs):
    fd, path = tempfile.mkstemp(*args, **kwargs)
    return (os.fdopen(fd, 'w'), path)

def post_data(data, url, curl_command="curl", use_curl=False, 
              content_type="text/xml", path=None, use_chunked=False, 
              is_odk=False):
    """
    Do a POST of data with some options.  Returns a tuple of the response
    from the server and any errors
    """
    results = None
    errors = None

    if path is not None:
        with open(path) as f:
            data = f.read()

    up = urlparse(url)
    try:
        if use_curl:
            if path is None:
                tmp_file, path = tmpfile()
                with tmp_file:
                    tmp_file.write(data)

            params = [curl_command, '--request', 'POST' ]
            params.append('--insecure')
            if is_odk == False:
                #it's legacy j2me
                params.append('--header')
                params.append('Content-type:%s' % content_type)
                params.append('--data-binary')
                params.append('@%s' % path)
            else:
                params.append('-F')
                params.append('xml_submission_file=@%s' % path)

            if use_chunked:
                params.append('--header')
                params.append('Transfer-encoding:chunked')
            else:
                if not is_odk:
                    params.append('--header')
                    params.append('"Content-length:%s"' % len(data))

            params.append(url)
            
            p = subprocess.Popen(params,
                                 stdout=PIPE,stderr=PIPE,shell=False)
            errors = p.stderr.read()
            results = p.stdout.read()
        else:
            headers = {
                "content-type": content_type,
                "content-length": len(data),
            }
            
            conn = httplib.HTTPSConnection(up.netloc) if url.startswith("https") else httplib.HTTPConnection(up.netloc) 
            conn.request('POST', up.path, data, headers)
            resp = conn.getresponse()
            results = resp.read()
    except Exception, e:
        errors = str(e)

    return (results,errors)
        
def post_file(filename, url, curl_command="curl", use_curl=False, content_type = "text/xml"):
    """
    Do a POST from file with some options.  Returns a tuple of the response
    from the server and any errors.
    """
    return post_data(None, url, curl_command, use_curl, content_type, filename)
