/* globals kmqPushSafe */

hqDefine("userreports/js/data_source_select", function() {
    $(function () {
        var dataSourceSelector = {
            application: ko.observable(""),
            sourceType: ko.observable(""),
            sourcesMap: hqImport("hqwebapp/js/initial_page_data").get("sources_map"),
            labelMap: {'case': gettext('Case'), 'form': gettext('Form')},
        };
        $("#report-builder-form").koApplyBindings(dataSourceSelector);
        $('#js-next-data-source').click(function () {
            window.analytics.usage('Report Builder v2', 'Data Source Next', s.capitalize(dataSourceSelector.sourceType()));
            kmqPushSafe(["trackClick", "rbv2_data_source", "RBv2 - Data Source"]);
        });
    });
});
