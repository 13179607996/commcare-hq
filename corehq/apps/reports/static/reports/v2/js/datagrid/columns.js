/**
 * todo add docstring
 */

hqDefine('reports/v2/js/datagrid/columns', [
    'jquery',
    'knockout',
    'underscore',
    'reports/v2/js/datagrid/filters',
], function (
    $,
    ko,
    _,
    filters
) {
    'use strict';

    var columnModel = function (data) {
        var self = {};

        self.title = ko.observable(data.title);
        self.name = ko.observable(data.name);
        self.width = ko.observable(data.width || 200);

        self.clause = ko.observable(data.clause || 'all');

        self.appliedFilters = ko.observableArray(_.map(data.appliedFilters, function (filterData) {
            return filters.appliedColumnFilter(filterData);
        }));

        self.showClause = ko.computed(function () {
            return self.appliedFilters().length > 0;
        });

        self.showAddFilter = ko.computed(function () {
            return self.appliedFilters().length < 2;
        });

        self.unwrap = function () {
            return ko.mapping.toJS(self);
        };

        self.context = ko.computed(function () {
            return {
                name: self.name(),
                clause: self.clause(),
                filters: _.map(self.appliedFilters(), function (filterData) {
                    return {
                        filterName: filterData.filterName(),
                        choiceName: filterData.choiceName(),
                        value: filterData.value() || '',
                    };
                }),
            };
        });

        return self;
    };

    var editColumnController = function (options) {
        var self = {};

        self.endpoint = options.endpoint;
        self.columnNameOptions = ko.observableArray();

        self.oldColumn = ko.observable();
        self.column = ko.observable();
        self.isNew = ko.observable();
        self.hasFilterUpdate = ko.observable(false);

        self.availableFilters = ko.observableArray(_.map(options.availableFilters, function (data) {
            return filters.columnFilter(data);
        }));

        self.availableFilterNames = ko.computed(function () {
            return _.map(self.availableFilters(), function (filter) {
                return filter.name();
            });
        });

        self.filterTitleByName = _.object(_.map(self.availableFilters(), function (filter) {
            return [filter.name(), filter.title()];
        }));

        self.selectedFilter = ko.computed(function () {
            var selected = self.availableFilters()[0];

            if (self.column() && self.column().appliedFilters().length > 0) {
                _.each(self.availableFilters(), function (filter) {
                    if (filter.name() === self.column().appliedFilters()[0].filterName()) {
                        selected = filter;
                    }
                });
            }
            return selected;
        });

        self.isFilterText = ko.computed(function () {
            return self.selectedFilter().type() === 'text';
        });

        self.isFilterNumeric = ko.computed(function () {
            return self.selectedFilter().type() === 'numeric';
        });

        self.availableChoiceNames = ko.computed(function () {
            return _.map(self.selectedFilter().choices(), function (choice) {
                return choice.name();
            });
        });

        self.choiceTitleByName = ko.computed(function () {
            return _.object(_.map(self.selectedFilter().choices(), function (choice) {
                return [choice.name(), choice.title()];
            }));
        });

        self.init = function (reportContextObservable) {
            self.reportContext = reportContextObservable;
        };

        self.setNew = function () {
            self.loadOptions();
            self.oldColumn(undefined);

            if (self.isNew() && self.column()) {
                // keep state of existing add column progress
                self.column(columnModel(self.column().unwrap()));
            } else {
                self.column(columnModel({}));
                self.isNew(true);
                self.hasFilterUpdate(false);
            }
        };

        self.set = function (existingColumn) {
            self.loadOptions();
            self.oldColumn(columnModel(existingColumn).unwrap());
            self.column(columnModel(existingColumn.unwrap()));
            self.isNew(false);
            self.hasFilterUpdate(false);
        };

        self.unset = function () {
            self.oldColumn(undefined);
            self.column(undefined);
            self.isNew(false);
            self.hasFilterUpdate(false);
        };

        self.addFilter = function () {
            self.column().appliedFilters.push(filters.appliedColumnFilter({
                filterName: self.selectedFilter().name(),
                choiceName: self.selectedFilter().choices()[0].name(),
            }));
            self.hasFilterUpdate(true);
        };

        self.removeFilter = function (deletedFilter) {
            self.column().appliedFilters.remove(function (filter) {
                return filter === deletedFilter;
            });
            self.hasFilterUpdate(true);
        };

        self.updateFilterName = function () {
            var name = self.selectedFilter().name();
            _.each(self.column().appliedFilters(), function (filter) {
                if (filter.filterName() !== name) {
                    filter.filterName(name);
                }
            });
            self.hasFilterUpdate(true);
        };

        self.updateFilter = function () {
            self.hasFilterUpdate(true);
        };

        self.loadOptions = function () {
            if (!self.reportContext) {
                throw new Error("Please call init() before calling loadOptions().");
            }

            $.ajax({
                url: self.endpoint.getUrl(),
                method: 'post',
                dataType: 'json',
                data: {
                    reportContext: JSON.stringify(self.reportContext()),
                },
            })
                .done(function (data) {
                    self.columnNameOptions(data.options);
                });
        };

        self.isColumnValid = ko.computed(function () {
            if (self.column()) {
                return !!self.column().title() && !!self.column().name();
            }
            return false;
        });

        self.isSaveDisabled = ko.computed(function () {
            return !self.isColumnValid();
        });

        return self;
    };

    return {
        columnModel: columnModel,
        editColumnController: editColumnController,
    };
});
