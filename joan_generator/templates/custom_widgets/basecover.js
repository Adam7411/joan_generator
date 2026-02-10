function basecover(widget_id, url, skin, parameters) {
    self = this;
    self.widget_id = widget_id;
    self.parameters = parameters;

    self.OnOpenClick = OnOpenClick;
    self.OnCloseClick = OnCloseClick;
    self.OnStopClick = OnStopClick;

    var callbacks = [
        { "selector": '#' + widget_id + ' #open', "action": "click", "callback": self.OnOpenClick },
        { "selector": '#' + widget_id + ' #close', "action": "click", "callback": self.OnCloseClick },
        { "selector": '#' + widget_id + ' #stop', "action": "click", "callback": self.OnStopClick }
    ];

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;

    var monitored_entities = [
        { "entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate }
    ];

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

    function OnStateAvailable(self, state) {
        self.state = state.state;
        set_view(self, self.state);
    }

    function OnStateUpdate(self, state) {
        self.state = state.state;
        set_view(self, self.state);
    }

    function OnOpenClick(self) {
        var args = {
            "service": "cover/open_cover",
            "entity_id": self.parameters.entity
        };
        self.call_service(self, args);
    }

    function OnCloseClick(self) {
        var args = {
            "service": "cover/close_cover",
            "entity_id": self.parameters.entity
        };
        self.call_service(self, args);
    }

    function OnStopClick(self) {
        var args = {
            "service": "cover/stop_cover",
            "entity_id": self.parameters.entity
        };
        self.call_service(self, args);
    }

    function set_view(self, state) {
        if (state === "open") {
            self.set_icon(self, "icon", self.icons.icon_open);
            self.set_field(self, "icon_style", self.css.icon_style_active);
        } else if (state === "closed") {
            self.set_icon(self, "icon", self.icons.icon_closed);
            self.set_field(self, "icon_style", self.css.icon_style_inactive);
        } else {
            // Unknown or other state
            self.set_icon(self, "icon", self.icons.icon_closed); // Default
            self.set_field(self, "icon_style", self.css.icon_style_inactive);
        }
    }
}
