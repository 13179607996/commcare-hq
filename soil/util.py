from django.conf import settings
from django.template import RequestContext
from django.utils import importlib
from soil import FileDownload, DownloadBase
from soil.exceptions import TaskFailedError
from soil.heartbeat import heartbeat_enabled, is_alive


def get_default_backend():
    """
    Get default export class. To override set it in your settings.
    
    This defaults to FileDownload.
    """
    if hasattr(settings, "SOIL_BACKEND"):
        # Trying to import the given backend, in case it's a dotted path
        backend = settings.SOIL_BACKEND
        mod_path, cls_name = backend.rsplit('.', 1)
        try:
            mod = importlib.import_module(mod_path)
            return getattr(mod, cls_name)
        except (AttributeError, ImportError):
            raise ValueError("Could not find soil backend '%s'" % backend)
    
    return FileDownload
        
def expose_download(payload, expiry, backend=None, **kwargs):
    """
    Expose a download object. Fully customizable, but allows 
    you to rely on global defaults if you don't care how things
    are stored.
    """
    if backend is None:
        backend = get_default_backend()
    
    ref = backend.create(payload, expiry, **kwargs)
    ref.save(expiry)
    return ref

def get_request_context(request, download_id):
    download_data = DownloadBase.get(download_id)
    if download_data is None:
        download_data = DownloadBase(download_id=download_id)
        is_ready = False
        try:
            if download_data.task.failed():
                raise TaskFailedError()
        except (TypeError, NotImplementedError):
            # no result backend / improperly configured
            pass
    else:
        is_ready=True
    alive = True
    if heartbeat_enabled():
        alive = is_alive()

    context = RequestContext(request)
    context['is_ready'] = is_ready
    context['is_alive'] = alive
    context['progress'] = download_data.get_progress()
    context['download_id'] = download_id
    return context
