function(doc) {
  if (doc.doc_type == 'XFormInstance') {
  var d = new Date(doc.form.meta.timeEnd);
  emit([doc.domain, doc.form.meta.userID, d.getFullYear(), d.getMonth()+1], null);
}
}