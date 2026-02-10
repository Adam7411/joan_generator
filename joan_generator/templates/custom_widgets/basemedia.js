function basemedia(widget_id, url, skin, parameters) {
    var self = this;
    self.widget_id = widget_id;
    self.parameters = parameters;

    // Define defaults for icons if not present in parameters/icons
    var default_icons = {
        "play_icon": "mdi-play",
        "pause_icon": "mdi-pause",
        "stop_icon": "mdi-stop",
        "previous_icon": "mdi-skip-previous",
        "next_icon": "mdi-skip-next",
        "icon_up": "mdi-volume-plus",
        "icon_down": "mdi-volume-minus"
    };

    // Ensure self.icons exists and populate with defaults if missing
    if (!self.icons) self.icons = {};
    for (var key in default_icons) {
        if (!self.icons[key]) {
            self.icons[key] = default_icons[key];
        }
    }

    self.OnPlayButtonClick = OnPlayButtonClick;
    self.OnPreviousButtonClick = OnPreviousButtonClick;
    self.OnNextButtonClick = OnNextButtonClick;
    self.OnRaiseLevelClick = OnRaiseLevelClick;
    self.OnLowerLevelClick = OnLowerLevelClick;

    self.min_level = 0;
    self.max_level = 1;

    if ("step" in self.parameters) {
        self.step = self.parameters.step / 100;
    } else {
        self.step = 0.05; // 5% default
    }

    var callbacks = [
        { "selector": '#' + widget_id + ' #play', "action": "click", "callback": self.OnPlayButtonClick },
        { "selector": '#' + widget_id + ' #level-up', "action": "click", "callback": self.OnRaiseLevelClick },
        { "selector": '#' + widget_id + ' #level-down', "action": "click", "callback": self.OnLowerLevelClick },
        { "selector": '#' + widget_id + ' #previous', "action": "click", "callback": self.OnPreviousButtonClick },
        { "selector": '#' + widget_id + ' #next', "action": "click", "callback": self.OnNextButtonClick }
    ];

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;

    var monitored_entities = [
        { "entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate }
    ];

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

    function OnStateAvailable(self, state) {
        self.entity = state.entity_id;
        self.level = state.attributes.volume_level || 0;
        self.state = state;
        set_view(self, state);
    }

    function OnStateUpdate(self, state) {
        self.level = state.attributes.volume_level || 0;
        self.state = state;
        set_view(self, state);
    }

    // Helper to get service args safely
    function get_service_args(self, param_name, default_service, value_key, value) {
        var args = {};
        if (self.parameters[param_name]) {
            args = JSON.parse(JSON.stringify(self.parameters[param_name]));
        } else {
            args = { "service": default_service, "entity_id": self.parameters.entity };
        }
        if (value_key && value !== undefined) {
            args[value_key] = value;
        }
        return args;
    }

    function OnPlayButtonClick(self) {
        var state = self.state.state;
        if (state !== "playing") {
            self.call_service(self, get_service_args(self, "post_service_play_pause", "media_player/media_play_pause"));
        } else {
            self.call_service(self, get_service_args(self, "post_service_play_pause", "media_player/media_play_pause"));
        }
    }

    function OnPreviousButtonClick(self) {
        self.call_service(self, get_service_args(self, "post_service_previous", "media_player/media_previous_track"));
    }

    function OnNextButtonClick(self) {
        self.call_service(self, get_service_args(self, "post_service_next", "media_player/media_next_track"));
    }

    function OnRaiseLevelClick(self) {
        var current = self.level || 0;
        var new_level = Math.round((current + self.step) * 100) / 100;
        if (new_level > self.max_level) new_level = self.max_level;

        self.call_service(self, get_service_args(self, "post_service_level", "media_player/volume_set", "volume_level", new_level));
    }

    function OnLowerLevelClick(self) {
        var current = self.level || 0;
        var new_level = Math.round((current - self.step) * 100) / 100;
        if (new_level < self.min_level) new_level = self.min_level;

        self.call_service(self, get_service_args(self, "post_service_level", "media_player/volume_set", "volume_level", new_level));
    }

    function set_view(self, state) {
        // Safe style accessor
        var get_style = function (key) {
            // Check css object first, then parameters
            if (self.css && self.css[key]) return self.css[key];
            if (self.parameters[key]) return self.parameters[key];
            return "";
        };

        if (state.state === "playing") {
            self.set_field(self, "play_icon_style", get_style("icon_style_active"));
            self.set_icon(self, "play_icon", self.icons.pause_icon);
        } else {
            self.set_field(self, "play_icon_style", get_style("icon_style_inactive"));
            self.set_icon(self, "play_icon", self.icons.play_icon);
        }

        // Apply styles to other icons
        self.set_field(self, "next_icon_style", get_style("icon_style_active") || get_style("icon_style"));
        self.set_field(self, "previous_icon_style", get_style("icon_style_active") || get_style("icon_style"));
        self.set_field(self, "level_up_style", get_style("level_up_style") || get_style("icon_style"));
        self.set_field(self, "level_down_style", get_style("level_down_style") || get_style("icon_style"));

        // Icons for next/prev
        self.set_icon(self, "next_icon", self.icons.next_icon);
        self.set_icon(self, "previous_icon", self.icons.previous_icon);
        self.set_icon(self, "icon_up", self.icons.icon_up);
        self.set_icon(self, "icon_down", self.icons.icon_down);


        if (state.attributes.media_artist) {
            self.set_field(self, "artist", state.attributes.media_artist);
        } else {
            self.set_field(self, "artist", "");
        }

        if (state.attributes.media_album_name) {
            self.set_field(self, "album", state.attributes.media_album_name);
        } else {
            self.set_field(self, "album", "");
        }

        var name = "";
        if (state.attributes.media_title) {
            if (self.parameters.truncate_name) {
                name = state.attributes.media_title.substring(0, self.parameters.truncate_name);
            } else {
                name = state.attributes.media_title;
            }
        }
        self.set_field(self, "media_title", name);

        if (state.attributes.volume_level !== undefined) {
            self.set_field(self, "level", Math.round(state.attributes.volume_level * 100));
        } else {
            self.set_field(self, "level", 0);
        }
    }
}
