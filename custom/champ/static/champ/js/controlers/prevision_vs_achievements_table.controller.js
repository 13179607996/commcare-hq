/* global moment */

function PrevisionVsAchievementsTableController($scope, reportsDataService, filtersService) {
    var vm = this;
    vm.title = "Prevision VS Achievements Table";
    vm.data = {};

    var currentYear = new Date().getFullYear();

    var defaultStartDate = moment(new Date(currentYear, 0, 1)).format('YYYY-MM-DD');
    var defaultEndDate = moment().format('YYYY-MM-DD');
    var defaultDate = {startDate: defaultStartDate, endDate: defaultEndDate};

    vm.visit_date = defaultDate;
    vm.post_date = defaultDate;
    vm.first_art_date = defaultDate;
    vm.date_handshake = defaultDate;
    vm.date_last_vl_test = defaultDate;

    vm.filters = {
        visit_date_start: vm.visit_date.startDate,
        visit_date_end: vm.visit_date.endDate,
        post_date_start: vm.post_date.startDate,
        post_date_end: vm.post_date.endDate,
        first_art_date_start: vm.first_art_date.startDate,
        first_art_date_end: vm.first_art_date.endDate,
        date_handshake_start: vm.date_handshake.startDate,
        date_handshake_end: vm.date_handshake.endDate,
        date_last_vl_test_start: vm.date_last_vl_test.startDate,
        date_last_vl_test_end: vm.date_last_vl_test.endDate,
    };

    $scope.$watch(function () {
        return vm.visit_date;
    }, function (newValue, oldValue) {
        if (newValue === oldValue) {
            return;
        }
        vm.filters = {
            visit_date_start: vm.visit_date.startDate.format('YYYY-MM-DD'),
            visit_date_end: vm.visit_date.endDate.format('YYYY-MM-DD'),
        };
    }, true);

    $scope.$watch(function () {
        return vm.post_date;
    }, function (newValue, oldValue) {
        if (newValue === oldValue) {
            return;
        }
        vm.filters = {
            post_date_start: vm.post_date.startDate.format('YYYY-MM-DD'),
            post_date_end: vm.post_date.endDate.format('YYYY-MM-DD'),
        };
    }, true);

    $scope.$watch(function () {
        return vm.first_art_date;
    }, function (newValue, oldValue) {
        if (newValue === oldValue) {
            return;
        }
        vm.filters = {
            first_art_date_start: vm.first_art_date.startDate.format('YYYY-MM-DD'),
            first_art_date_end: vm.first_art_date.endDate.format('YYYY-MM-DD'),
        };
    }, true);

    $scope.$watch(function () {
        return vm.date_handshake;
    }, function (newValue, oldValue) {
        if (newValue === oldValue) {
            return;
        }
        vm.filters = {
            date_last_vl_test_start: vm.date_last_vl_test.startDate.format('YYYY-MM-DD'),
            date_last_vl_test_end: vm.date_last_vl_test.endDate.format('YYYY-MM-DD'),
        };
    }, true);

    $scope.$watch(function () {
        return vm.visit_date;
    }, function (newValue, oldValue) {
        if (newValue === oldValue) {
            return;
        }
        vm.filters = {
            visit_date_start: vm.visit_date.startDate.format('YYYY-MM-DD'),
            visit_date_end: vm.visit_date.endDate.format('YYYY-MM-DD'),
        };
    }, true);

    vm.pickerOptions = {
        opens: "left",
        drops: "up",
        showDropdowns: true,
        locale: {
            format: "YYYY-MM-DD",
        }
    };

    vm.getData = function() {
        reportsDataService.getPrevisionVsAchievementsTableData(vm.filters).then(function (response) {
            vm.data = response.data;
            filtersService.districtFilter().then(function (response) {
                vm.districts = response.data.options;
            });
        });
    };
    vm.getData();
}

PrevisionVsAchievementsTableController.$inject = ['$scope', 'reportsDataService', 'filtersService'];