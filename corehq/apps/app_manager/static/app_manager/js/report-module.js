
var ReportModule = (function () {

    function Config(dict) {
        var self = this;

        var dict = dict || {};
        self.keyValuePairs = ko.observableArray();
        for (var key in dict) {
            self.keyValuePairs.push([ko.observable(key), ko.observable(dict[key])]);
        }

        self.addConfig = function() {
            self.keyValuePairs.push([ko.observable(''), ko.observable('')]);
        };
    };

    function GraphConfig(report_id, reportId, availableReportIds, reportCharts, graph_configs) {
        var self = this;

        graph_configs = graph_configs || {};

        this.graphConfigs = {};
        for (var i = 0; i < availableReportIds.length; i++) {
            var currentReportId = availableReportIds[i];
            self.graphConfigs[currentReportId] = {};
            for (var j = 0; j < reportCharts[currentReportId].length; j++) {
                var currentChart = reportCharts[currentReportId][j];
                var graph_config = graph_configs[currentChart.chart_id] || {};
                var series_config = {};
                var chart_series = [];
                for(var k = 0; k < currentChart.y_axis_columns.length; k++) {
                    var series = currentChart.y_axis_columns[k];
                    chart_series.push(series);
                    series_config[series] = new Config(
                        currentReportId == report_id ? (graph_config.series_config || {})[series] || {} : {}
                    );
                }

                self.graphConfigs[currentReportId][currentChart.chart_id] = {
                    graph_type: ko.observable(currentReportId == report_id ? graph_config.graph_type || 'bar' : 'bar'),
                    series_config: series_config,
                    chart_series: chart_series,
                    config: new Config(
                        currentReportId == report_id ? graph_config.config || {} : {}
                    )
                }
            }
        }

        this.currentGraphConfigs = ko.computed(function() {
            return self.graphConfigs[reportId()];
        });

        this.currentCharts = ko.computed(function() {
            return reportCharts[reportId()];
        });

        this.getCurrentGraphConfig = function(chart_id) {
            return self.currentGraphConfigs()[chart_id] || {};
        };

        this.toJSON = function () {
            function configToDict(config) {
                var dict = {};
                var keyValuePairs = config.keyValuePairs();
                for (var i = 0; i < keyValuePairs.length; i++) {
                    dict[keyValuePairs[i][0]()] = keyValuePairs[i][1]();
                }
                return dict;
            }

            var chartsToConfigs = {};
            var currentChartsToConfigs = self.currentGraphConfigs();
            for (var chart_id in currentChartsToConfigs) {
                var graph_config = currentChartsToConfigs[chart_id];
                chartsToConfigs[chart_id] = {
                    series_config: {}
                };
                for (var series in graph_config.series_config) {
                    chartsToConfigs[chart_id].series_config[series] = configToDict(graph_config.series_config[series])
                }
                chartsToConfigs[chart_id].graph_type = graph_config.graph_type();
                chartsToConfigs[chart_id].config = configToDict(graph_config.config);
            }
            return chartsToConfigs;
        };
    }

    function ReportConfig(report_id, display, availableReportIds, reportCharts, graph_configs, language) {
        var self = this;
        this.lang = language;
        this.fullDisplay = display || {};
        this.availableReportIds = availableReportIds;
        this.display = ko.observable(this.fullDisplay[this.lang]);
        this.reportId = ko.observable(report_id);
        this.graphConfig = new GraphConfig(report_id, this.reportId, availableReportIds, reportCharts, graph_configs);
        this.toJSON = function () {
            self.fullDisplay[self.lang] = self.display();
            return {
                report_id: self.reportId(),
                graph_configs: self.graphConfig.toJSON(),
                header: self.fullDisplay
            };
        };
    }
    function ReportModule(options) {
        var self = this;
        var currentReports = options.currentReports || [];
        var availableReports = options.availableReports || [];
        var saveURL = options.saveURL;
        self.lang = options.lang;
        self.moduleName = options.moduleName;
        self.currentModuleName = ko.observable(options.moduleName[self.lang]);
        self.reportTitles = {};
        self.reportCharts = {};
        self.reports = ko.observableArray([]);
        for (var i = 0; i < availableReports.length; i++) {
            var report = availableReports[i];
            var report_id = report.report_id;
            self.reportTitles[report_id] = report.title;
            self.reportCharts[report_id] = report.charts;
        }

        self.availableReportIds = _.map(options.availableReports, function (r) { return r.report_id; });

        self.defaultReportTitle = function (reportId) {
            return self.reportTitles[reportId];
        };

        self.saveButton = COMMCAREHQ.SaveButton.init({
            unsavedMessage: "You have unsaved changes in your report list module",
            save: function () {
                // validate that all reports have valid data
                var reports = self.reports();
                for (var i = 0; i < reports.length; i++) {
                    if (!reports[i].reportId() || !reports[i].display()) {
                        alert('Reports must have all properties set!');
                    }
                }
                self.moduleName[self.lang] = self.currentModuleName();
                self.saveButton.ajax({
                    url: saveURL,
                    type: 'post',
                    dataType: 'json',
                    data: {
                        name: JSON.stringify(self.moduleName),
                        reports: JSON.stringify(_.map(self.reports(), function (r) { return r.toJSON(); }))
                    }
                });
            }
        });

        var changeSaveButton = function () {
            self.saveButton.fire('change');
        };

        self.currentModuleName.subscribe(changeSaveButton);

        function newReport(options) {
            options = options || {};
            var report = new ReportConfig(
                options.report_id,
                options.header,
                self.availableReportIds,
                self.reportCharts,
                options.graph_configs,
                self.lang
            );
            report.display.subscribe(changeSaveButton);
            report.reportId.subscribe(changeSaveButton);
            report.reportId.subscribe(function (reportId) {
                report.display(self.defaultReportTitle(reportId));
            });

            return report;
        }
        this.addReport = function () {
            self.reports.push(newReport());
        };
        this.removeReport = function (report) {
            self.reports.remove(report);
            changeSaveButton();
        };

        // add exiting reports to UI
        for (i = 0; i < currentReports.length; i += 1) {
            var report = newReport(currentReports[i]);
            self.reports.push(report);
        }
    }

    return ReportModule;
}());
