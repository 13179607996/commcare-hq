(function () {
    'use strict';

    var getLocalDate = function (date) {
        /**
         * This fixes an issue with daterangepicker where a date is passed in
         * then converted to the browser's local timezone. So if you are in
         * EST that means the date shows up as the day before.
         */
        var _date = new Date(date);
        _date.setMinutes(_date.getMinutes() + _date.getTimezoneOffset());
        return _date;
    };
    $.fn.getDateRangeSeparator = function () {
        return ' to ';
    };
    $.fn.createDateRangePicker = function(
        range_labels, separator, startdate, enddate
    ) {
        var now = moment();
        var ranges = {};
        ranges[range_labels.last_7_days] = [
            moment().subtract('7', 'days').startOf('days'),
        ];

        ranges[range_labels.last_month] = [
            moment().subtract('1', 'months').startOf('month'),
            moment().subtract('1', 'months').endOf('month'),
        ];

        ranges[range_labels.last_30_days] = [
            moment().subtract('30', 'days').startOf('days'),
        ];
        var config = {
            showDropdowns: true,
            ranges: ranges,
            timePicker: false,
            locale: {
                format: 'YYYY-MM-DD',
                separator: separator,
                cancelLabel: gettext('Clear'),
            },
        };
        var hasStartAndEndDate = !_.isEmpty(startdate) && !_.isEmpty(enddate);
        if (hasStartAndEndDate) {
            config.startDate = getLocalDate(startdate);
            config.endDate = getLocalDate(enddate);
        }

        $(this).daterangepicker(config);

        var $el = $(this);
        $el.daterangepicker(config);
        $el.on('cancel.daterangepicker', function() {

            // Clear startdate and enddate filters
            var filter_id = $(this)[0].getAttribute("name");
            var filter_id_start = filter_id + "-start";
            var filter_id_end = filter_id + "-end";
            if (document.getElementById(filter_id_start) && document.getElementById(filter_id_end)) {
                document.getElementById(filter_id_start).setAttribute("value", "");
                document.getElementById(filter_id_end).setAttribute("value", "");
            }

            $el.val(gettext("Show All"));
        });

        if (! hasStartAndEndDate){
            $(this).val("");
        }
    };
    $.fn.createBootstrap3DefaultDateRangePicker = function () {
        this.createDateRangePicker(
            {
                last_7_days: 'Last 7 Days',
                last_month: 'Last Month',
                last_30_days: 'Last 30 Days',
            },
            this.getDateRangeSeparator()
        );
    };
})();
