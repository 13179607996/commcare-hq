from soil import DownloadBase, CachedDownload, FileDownload
from soil.exceptions import TaskFailedError
from soil.heartbeat import heartbeat_enabled, is_alive


def expose_cached_download(payload, expiry, **kwargs):
    """
    Expose a cache download object.
    """
    ref = CachedDownload.create(payload, expiry, **kwargs)
    ref.save(expiry)
    return ref


def expose_file_download(path, **kwargs):
    """
    Expose a file download object that potentially uses the external drive
    """
    ref = FileDownload.create(path, **kwargs)
    ref.save()
    return ref


def get_download_context(download_id, check_state=False):
    is_ready = False
    context = {}
    download_data = DownloadBase.get(download_id)
    context['has_file'] = bool(download_data)
    if download_data is None:
        download_data = DownloadBase(download_id=download_id)

    try:
        if download_data.task.failed():
            raise TaskFailedError()
    except (TypeError, NotImplementedError):
        # no result backend / improperly configured
        pass
    else:
        if not check_state:
            is_ready = True
        elif download_data.task.state == 'SUCCESS':
            is_ready = True
            result = download_data.task.result
            context['result'] = result and result.get('messages')

    alive = True
    if heartbeat_enabled():
        alive = is_alive()

    context['is_ready'] = is_ready
    context['is_alive'] = alive
    context['progress'] = download_data.get_progress()
    context['download_id'] = download_id
    return context
