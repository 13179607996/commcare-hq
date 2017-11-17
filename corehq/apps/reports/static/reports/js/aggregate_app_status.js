/* globals d3, django, moment, nv */
hqDefine("reports/js/aggregate_app_status", function() {
    function setupCharts(data, div) {
        nv.addGraph(function() {
        var chart = nv.models.multiBarChart()
          .transitionDuration(100)
          .showControls(false)
          .reduceXTicks(true)
          .rotateLabels(0)
          .groupSpacing(0.1)
        ;

        chart.yAxis
            .tickFormat(d3.format(',f'));

        d3.select('#' + div + ' svg')
            .datum([data])
            .call(chart);

        nv.utils.windowResize(chart.update);
        return chart;
    });

    }
    $(document).ajaxSuccess(function(event, xhr, settings) {
        if (settings.url.match(/reports\/async\/aggregate_user_status/)) {
            setupCharts($("#submission-data").data("value"), 'submission_dates');
            setupCharts($("#sync-data").data("value"), 'sync_dates');
            $('.chart-toggle').click(function () {
                $(this).parent().children().not(this).removeClass('btn-primary');
                $(this).addClass('btn-primary');
                setupCharts($("#" + $(this).data('chart-data')).data("value"), $(this).data('chart-div'));
            })
        }
    });
});
