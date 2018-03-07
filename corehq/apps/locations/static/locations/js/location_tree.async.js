/* globals django */
hqDefine('locations/js/location_tree', function() {
    function api_get_children(loc_uuid, show_inactive, load_locs_url, callback) {
        var params = (loc_uuid ? {
            parent_id: loc_uuid,
        } : {});
        params.include_inactive = show_inactive;
        $.getJSON(load_locs_url, params, function(allData) {
            callback(allData.objects);
        });
    }

    function LocationTreeViewModel(hierarchy, options) {
        // options should have properties:
        //      "can_edit_root"
        //      "load_locs_url"
        //      "new_loc_url"
        //      "loc_edit_url"
        //      "reloadLocationSearchSelect"
        //      "clearLocationSelection"

        var model = this;

        this.root = ko.observable();

        // TODO this should reference location type settings for domain
        this.location_types = $.map(hierarchy, function(e) {
            return {
                type: e[0],
                allowed_parents: e[1],
            };
        });

        // search for a location within the tree by uuid; return path to location if found
        this.find_loc = function(uuid, loc) {
            loc = loc || this.root();

            if (loc.uuid() === uuid) {
                return [loc];
            } else {
                var path = null;
                $.each(loc.children(), function(i, e) {
                    var subpath = model.find_loc(uuid, e);
                    if (subpath) {
                        path = subpath;
                        path.splice(0, 0, loc);
                        return false;
                    }
                });
                return path;
            }
        };

        // load location hierarchy
        this.load = function (locs) {
            this.root(new LocationModel({
                name: '_root',
                children: locs,
                can_edit: options.can_edit_root,
                expanded: true,
                reloadLocationSearchSelect: options.reloadLocationSearchSelect,
                clearLocationSelection: options.clearLocationSelection,
                new_loc_url: options.new_loc_url,
                loc_edit_url: options.loc_edit_url,
                load_locs_url: options.load_locs_url,
            }, this));
        };
    }

    function LocationSearchViewModel(tree_model, options) {
        // options should have properties:
        //      "can_edit_root"
        //      "load_locs_url"
        //      "new_loc_url"
        //      "loc_edit_url"
        //      "reloadLocationSearchSelect"
        //      "clearLocationSelection"

        var model = this;
        this.selected_location = ko.observable();
        this.l__selected_location_id = ko.observable();
        this.clearLocationSelection = ko.observable(options.clearLocationSelection);

        this.selected_location_id = ko.computed(function() {
            if (!model.l__selected_location_id()) {
                return;
            }
            return (model.l__selected_location_id().split("l__")[1]);
        });

        this.selected_location = ko.computed(function() {
            if (!model.selected_location_id()) {
                return;
            }
            return new LocationModel({
                uuid: model.selected_location_id(),
                can_edit: options.can_edit_root,
                is_archived: options.show_inactive,
                reloadLocationSearchSelect: options.reloadLocationSearchSelect,
                clearLocationSelection: options.clearLocationSelection,
                new_loc_url: options.new_loc_url,
                loc_edit_url: options.loc_edit_url,
                load_locs_url: options.load_locs_url,
            }, this);
        });

        this.selected_location_tree = tree_model;

        this.lineage = ko.computed(function() {
            if (!model.selected_location()) {
                return;
            }
            $.ajax({
                type: 'GET',
                url: model.selected_location().loc_lineage_url(model.selected_location().uuid()),
                dataType: 'json',
                error: 'error',
                success: function(response) {

                    var expand_tree = function() {
                        var child = null;
                        for (var lineage_idx = 0; lineage_idx < response.lineage.length; lineage_idx++) {
                            var location = response.lineage[lineage_idx];
                            var data = {
                                name: location.name,
                                location_type: location.location_type,
                                uuid: location.location_id,
                                is_archived: location.is_archived,
                                can_edit: options.can_edit_root,
                                children: child,
                                expanded: child ? 'semi' : false,
                                children_status: 'semi_loaded',
                                reloadLocationSearchSelect: options.reloadLocationSearchSelect,
                                clearLocationSelection: options.clearLocationSelection,
                                new_loc_url: options.new_loc_url,
                                loc_edit_url: options.loc_edit_url,
                                load_locs_url: options.load_locs_url,
                            };
                            var level = new LocationModel(data, tree_model, response.lineage.length - lineage_idx - 1);
                            child = Array.of(Object.assign({}, data));
                        }
                        var root_children = [];
                        for (var child_idx = 0; child_idx < tree_model.locs.length; child_idx++) {
                            if (tree_model.locs[child_idx].name === child[0].name) {
                                root_children.push(child[0]);
                            } else {
                                root_children.push(tree_model.locs[child_idx]);
                            }
                        }
                        level = new LocationModel({
                            name: '_root',
                            children: root_children,
                            can_edit: options.can_edit_root,
                            expanded: 'semi',
                            reloadLocationSearchSelect: options.reloadLocationSearchSelect,
                            clearLocationSelection: options.clearLocationSelection,
                            new_loc_url: options.new_loc_url,
                            loc_edit_url: options.loc_edit_url,
                            load_locs_url: options.load_locs_url,
                        }, tree_model);
                        return level;
                    };

                    tree_model.root(expand_tree());

                },
            });
        });
    }

    function LocationModel(data, root, depth) {
        var loc = this;
        var alert_user = hqImport("hqwebapp/js/alert_user").alert_user;

        this.name = ko.observable();
        this.type = ko.observable();
        this.uuid = ko.observable();
        this.is_archived = ko.observable();
        this.can_edit = ko.observable();
        this.children = ko.observableArray();
        this.depth = depth || 0;
        this.children_status = ko.observable('not_loaded');
        this.expanded = ko.observable(false);

        this.loc_edit_url = data.loc_edit_url;

        this.new_loc_url = data.new_loc_url;
        this.reloadLocationSearchSelect = data.reloadLocationSearchSelect;
        this.clearLocationSelection = data.clearLocationSelection;

        this.expanded.subscribe(function(val) {
            if (val === true && (this.children_status() === 'not_loaded' || this.children_status() === 'semi_loaded')) {
                this.load_children_async();
            }
        }, this);

        this.toggle = function() {
            if (this.expanded() === 'semi') {
                this.expanded(this.can_have_children());
            } else {
                this.expanded(!this.expanded() && this.can_have_children());
            }
        };

        this.load = function(data) {
            this.name(data.name);
            this.type(data.location_type);
            this.uuid(data.uuid);
            this.is_archived(data.is_archived);
            this.can_edit(data.can_edit);
            this.expanded(data.expanded);

            if (data.children_status !== null && data.children_status !== undefined) {
                this.children_status(data.children_status);
            }
            if (data.children !== null) {
                this.set_children(data.children, data);
            }
        };

        this.set_children = function(children, data) {
            var sortedChildren = [];
            if (children) {
                sortedChildren = _.sortBy(children, function(e) {
                    return e.name;
                });
            }

            if (loc.children().length > 0 && loc.name() !== "_root") {
                for (var child_idx = 0; child_idx < sortedChildren.length; child_idx++) {
                    if (sortedChildren[child_idx].name === loc.children()[0].name()) {
                        sortedChildren.splice(child_idx, 1);
                        break;
                    }
                }

                var model_children = $.map(sortedChildren, function(e) {
                    return new LocationModel(_.extend(e, {
                        loc_edit_url: data.loc_edit_url,
                        load_locs_url: data.load_locs_url,
                        new_loc_url: data.new_loc_url }), root, loc.depth + 1);
                });
                model_children.unshift(loc.children()[0]);
                this.children(model_children);
            } else {
                this.children($.map(sortedChildren, function (e) {
                    return new LocationModel(_.extend(e, {
                        loc_edit_url: data.loc_edit_url,
                        load_locs_url: data.load_locs_url,
                        new_loc_url: data.new_loc_url }), root, loc.depth + 1);
                }));
            }

            if (this.expanded() === true) {
                this.children_status('loaded');
            } else if (this.expanded() === 'semi') {
                this.children_status('semi_loaded');
            }
        };

        this.load_children_async = function(callback) {
            this.children_status('loading');
            api_get_children(this.uuid(), data.show_inactive, data.load_locs_url, function(resp) {
                loc.set_children(resp, {
                    loc_edit_url: data.loc_edit_url,
                    load_locs_url: data.load_locs_url,
                    new_loc_url: data.new_loc_url,
                });
                if (callback) {
                    callback(loc);
                }
            });
        };

        this.allowed_child_types = function() {
            var loc = this;
            var types = [];
            $.each(root.location_types, function(i, loc_type) {
                $.each(loc_type.allowed_parents, function(i, parent_type) {
                    if (loc.type() === parent_type) {
                        types.push(loc_type.type);
                    }
                });
            });
            return types;
        };

        this.can_have_children = ko.computed(function() {
            return (this.allowed_child_types().length > 0);
        }, this);

        this.allowed_child_type = function() {
            var types = this.allowed_child_types();
            return (types.length === 1 ? types[0] : null);
        };

        this.new_child_caption = ko.computed(function() {
            var child_type = this.allowed_child_type();
            var top_level = (this.name() === '_root');
            return 'New ' + (child_type || 'location') + (top_level ? ' at top level' : ' in ' + this.name() + ' ' + this.type());
        }, this);

        this.no_children_caption = ko.computed(function() {
            var top_level = (this.name() === '_root');

            // TODO replace 'location' with proper type as applicable (what about pluralization?)
            return (top_level ? 'No locations created in this project yet' : 'No child locations inside ' + this.name());
        }, this);

        this.show_archive_action_button = ko.computed(function() {
            return !data.show_inactive || this.is_archived();
        }, this);

        this.load(data);

        this.new_location_tracking = function() {
            hqImport('analytix/js/google').track.event('Organization Structure', '+ New _______');
            return true;
        };

        this.remove_elements_after_action = function(button) {
            $(button).closest('.loc_section').remove();
        };

        this.archive_success_message = _.template(django.gettext("You have successfully archived the location <%=name%>"));

        this.delete_success_message = _.template(django.gettext(
            "You have successfully deleted the location <%=name%> and all of its child locations"
        ));

        this.delete_error_message = _.template(django.gettext("An error occurred while deleting your location. If the problem persists, please report an issue"));

        this.loc_archive_url = function(loc_id) {
            var initial_page_data = hqImport('hqwebapp/js/initial_page_data');
            var template = initial_page_data.reverse('archive_location');
            return template.replace('-locid-', loc_id);
        };

        this.loc_unarchive_url = function(loc_id) {
            var initial_page_data = hqImport('hqwebapp/js/initial_page_data');
            var template = initial_page_data.reverse('unarchive_location');
            return template.replace('-locid-', loc_id);
        };

        this.loc_delete_url = function(loc_id) {
            var initial_page_data = hqImport('hqwebapp/js/initial_page_data');
            var template = initial_page_data.reverse('delete_location');
            return template.replace('-locid-', loc_id);
        };

        this.loc_lineage_url = function(loc_id) {
            var initial_page_data = hqImport('hqwebapp/js/initial_page_data');
            var template = initial_page_data.reverse('location_lineage');
            return template.replace('-locid-', loc_id);
        };

        this.loc_descendant_url = function(loc_id) {
            var initial_page_data = hqImport('hqwebapp/js/initial_page_data');
            var template = initial_page_data.reverse('location_descendants_count');
            return template.replace('-locid-', loc_id);
        };

        this.archive_loc = function(button, name, loc_id) {
            var archive_location_modal = $('#archive-location-modal')[0];

            function archive_fn() {
                $(button).disableButton();
                $.ajax({
                    type: 'POST',
                    url: loc.loc_archive_url(loc_id),
                    dataType: 'json',
                    error: 'error',
                    success: function() {
                        alert_user(loc.archive_success_message({
                            "name": name,
                        }), "success");
                        loc.remove_elements_after_action(button);
                        data.reloadLocationSearchSelect();
                    },
                });
                $(archive_location_modal).modal('hide');
                hqImport('analytix/js/google').track.event('Organization Structure', 'Archive');
            }

            var modal_context = {
                "name": name,
                "loc_id": loc_id,
                "archive_fn": archive_fn,
            };
            ko.cleanNode(archive_location_modal);
            $(archive_location_modal).koApplyBindings(modal_context);
            $(archive_location_modal).modal('show');
        };

        this.unarchive_loc = function(button, loc_id) {
            $(button).disableButton();
            $.ajax({
                type: 'POST',
                url: loc.loc_unarchive_url(loc_id),
                dataType: 'json',
                error: 'error',
                success: function() {
                    loc.remove_elements_after_action(button);
                    data.reloadLocationSearchSelect();
                },
            });
        };

        this.delete_loc = function(button, name, loc_id) {
            var delete_location_modal = $('#delete-location-modal')[0];
            var modal_context;

            function delete_fn() {
                if (modal_context.count === parseInt(modal_context.signOff())) {
                    $(button).disableButton();

                    $.ajax({
                        type: 'DELETE',
                        url: loc.loc_delete_url(loc_id),
                        dataType: 'json',
                        error: function() {
                            alert_user(loc.delete_error_message, "warning");
                            $(button).enableButton();
                        },
                        success: function(response) {
                            if (response.success) {
                                alert_user(loc.delete_success_message({
                                    "name": name,
                                }), "success");
                                loc.remove_elements_after_action(button);
                                data.reloadLocationSearchSelect();
                            } else {
                                alert_user(response.message, "warning");

                            }
                        },
                    });
                    $(delete_location_modal).modal('hide');
                    hqImport('analytix/js/google').track.event('Organization Structure', 'Delete');
                }
            }

            $.ajax({
                type: 'GET',
                url: this.loc_descendant_url(loc_id),
                dataType: 'json',
                success: function(response) {
                    modal_context = {
                        "name": name,
                        "loc_id": loc_id,
                        "delete_fn": delete_fn,
                        "count": response.count,
                        "signOff": ko.observable(''),
                    };
                    ko.cleanNode(delete_location_modal);
                    ko.applyBindings(modal_context, delete_location_modal);
                    $(delete_location_modal).modal('show');
                },
            });
        };
    }

    return {
        LocationSearchViewModel: LocationSearchViewModel,
        LocationTreeViewModel: LocationTreeViewModel,
        LocationModel: LocationModel,
    };
});
