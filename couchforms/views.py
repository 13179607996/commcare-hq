from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from couchforms.util import post_xform_to_couch
from django.http import HttpResponse, HttpResponseServerError
import logging
from couchforms.models import XFormInstance

@require_POST
@csrf_exempt
def post(request, callback=None):
    """
    XForms can get posted here.  They will be forwarded to couch.
    
    Just like play, if you specify a callback you get called, 
    otherwise you get a generic response.  Callbacks follow
    a different signature as play, only passing in the document
    (since we don't know what xform was being posted to)
    """
    # odk/javarosa preprocessing. These come in in different ways.
    if request.META['CONTENT_TYPE'].startswith('multipart/form-data'):
        #it's an standard form submission (eg ODK)
        #this does an assumption that ODK submissions submit using the form parameter xml_submission_file
        #todo: this should be made more flexibly to handle differeing params for xform submission
        instance = request.FILES['xml_submission_file'].read()
        for key, item in request.FILES.items():
            if key != "xml_submission_file":
                pass
                # TODO: this is where we handle multimedia... somehow
            
    else:
        #else, this is a raw post via a j2me client of xml (or touchforms)
        #todo, multipart raw submissions need further parsing capacity.
        instance = request.raw_post_data

    #todo:  also multipart submissions be it odk or j2me need to be attached to instance after the document is created in couch.
    try:
        doc = post_xform_to_couch(instance)
        if callback:
            return callback(doc)
        return HttpResponse("Thanks! Your new xform id is: %s" % doc["_id"])
    except Exception, e:
        logging.exception(e)
        return HttpResponseServerError("FAIL")

def download_form(request, instance_id):
    instance = XFormInstance.get(instance_id) 
    response = HttpResponse(mimetype='application/xml')
    response.write(instance.get_xml())
    # if we want it to download like a file put somethingl like this
    # HttpResponse(mimetype='application/vnd.ms-excel')
    # response['Content-Disposition'] = 'attachment; filename=%s.xml' % instance_id
    return response