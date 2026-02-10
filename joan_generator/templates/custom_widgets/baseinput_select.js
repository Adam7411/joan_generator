function baseinput_select(widget_id, url, skin, parameters) {
    self = this;
    self.widget_id = widget_id;
    self.parameters = parameters;

    self.OnNextClick = OnNextClick;

    var callbacks = [
        { "selector": '#' + widget_id, "action": "click", "callback": self.OnNextClick }
    ];

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;

    var monitored_entities = [
        { "entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate }
    ];

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

    function OnStateAvailable(self, state) {
        self.state = state.state;
        self.attributes = state.attributes;
        set_view(self, self.state);
    }

    function OnStateUpdate(self, state) {
        self.state = state.state;
        self.attributes = state.attributes;
        set_view(self, self.state);
    }

    function OnNextClick(self) {
        var options = self.attributes.options || [];
        var current = self.state;
        var idx = options.indexOf(current);
        var next_idx = (idx + 1) % options.length;
        var next_val = options[next_idx];

        var args = {
            "service": "input_select/select_option",
            "entity_id": self.parameters.entity,
            "option": next_val
        };
        self.call_service(self, args);
    }

    function set_view(self, state) {
        self.set_field(self, "selected_option", state);
    }
}
