hqDefine('export/js/download_export', function () {
    'use strict';

    /*var initial_page_data = hqImport('hqwebapp/js/initial_page_data').get;
    var downloadExportsApp = window.angular.module('downloadExportsApp', ['hq.download_export']);
    downloadExportsApp.config(["djangoRMIProvider", function (djangoRMIProvider) {
        djangoRMIProvider.configure(initial_page_data('djng_current_rmi'));
    }]);
    downloadExportsApp.constant('exportList', initial_page_data('export_list'));
    downloadExportsApp.constant('maxColumnSize', initial_page_data('max_column_size'));
    downloadExportsApp.constant('defaultDateRange', initial_page_data('default_date_range'));
    downloadExportsApp.constant('checkForMultimedia', initial_page_data('check_for_multimedia'));
    downloadExportsApp.constant('formElement', {
        progress: function () {
            return $('#download-progress-bar');
        },
        group: function () {
            return $('#id_group');
        },
        user_type: function () {
            return $('#id_user_types');
        },
    });*/

    var downloadExportModel = function (options) {
        var self = {};

        self.exportList = options.exportList;

        return self;
    };

    $(function () {
        hqImport("reports/js/filters/main").init();

        var initialPageData = hqImport("hqwebapp/js/initial_page_data");
        $("#download-export").koApplyBindings(downloadExportModel({
            exportList: initialPageData.get('export_list'),
        }));

        $(".hqwebapp-datespan").each(function () {
            var $el = $(this).find("input");
            $el.createDateRangePicker(
                $el.data("labels"),
                $el.data("separator"),
                $el.data('startDate'),
                $el.data('endDate')
            );
        });
    });
});
