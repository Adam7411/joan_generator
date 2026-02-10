function basefan(widget_id, url, skin, parameters) {
    self = this;

    // Initialization

    self.widget_id = widget_id;

    // Parameters may come in useful later on

    self.parameters = parameters;

    self.OnPowerButtonClick = OnPowerButtonClick;
    self.On1ButtonClick = On1ButtonClick;
    self.On2ButtonClick = On2ButtonClick;
    self.On3ButtonClick = On3ButtonClick;

    var callbacks =
        [

            { "selector": '#' + widget_id + ' #power', "action": "click", "callback": self.OnPowerButtonClick },
            { "selector": '#' + widget_id + ' #speed1', "action": "click", "callback": self.On1ButtonClick },
            { "selector": '#' + widget_id + ' #speed2', "action": "click", "callback": self.On2ButtonClick },
            { "selector": '#' + widget_id + ' #speed3', "action": "click", "callback": self.On3ButtonClick }
        ];

    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;

    var monitored_entities =
        [
            { "entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate }
        ];

    // Finally, call the parent constructor to get things moving

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

    // Function Definitions

    // The StateAvailable function will be called when
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state

    function OnStateAvailable(self, state) {
        self.state = state;
        set_view(self, state)
    }

    // The OnStateUpdate function will be called when the specific entity
    // receives a state update - its new values will be available
    // in self.state[<entity>] and returned in the state parameter

    function OnStateUpdate(self, state) {
        self.state = state;
        set_view(self, state)
    }

    function OnPowerButtonClick(self) {
        var args = {};
        if (self.state.state == "off") {
            // FIX: Clone param
            args = JSON.parse(JSON.stringify(self.parameters.post_service_active));
        }
        else {
            // FIX: Clone param
            args = JSON.parse(JSON.stringify(self.parameters.post_service_inactive));
        }
        self.call_service(self, args);
    }

    function On1ButtonClick(self) {
        // FIX: Clone param
        var args = JSON.parse(JSON.stringify(self.parameters.post_service_speed));
        args["speed"] = self.parameters.fields.low_speed;
        // For HA Fan integration, it might be percentage, but let's stick to what the widget expects.
        // run.py passes raw values.
        self.call_service(self, args);
    }
    function On2ButtonClick(self) {
        // FIX: Clone param
        var args = JSON.parse(JSON.stringify(self.parameters.post_service_speed));
        args["speed"] = self.parameters.fields.medium_speed;
        self.call_service(self, args);
    }
    function On3ButtonClick(self) {
        // FIX: Clone param
        var args = JSON.parse(JSON.stringify(self.parameters.post_service_speed));
        args["speed"] = self.parameters.fields.high_speed;
        self.call_service(self, args);
    }


    function set_view(self, state) {

        if (state.state != "on") {
            self.set_icon(self, "icon", self.icons.icon_inactive)
            self.set_field(self, "icon_style", self.css.icon_style_active) // Changed from inactive to match active logic typically? Or leave as original? Original was inactive.
            self.set_field(self, "icon_style", self.css.icon_style_inactive)

            self.set_field(self, "speed1_style", self.css.speed1_style_inactive)
            self.set_field(self, "speed2_style", self.css.speed2_style_inactive)
            self.set_field(self, "speed3_style", self.css.speed3_style_inactive)
            self.set_icon(self, "icon1", self.icons.icon1_inactive)
            self.set_icon(self, "icon2", self.icons.icon2_inactive)
            self.set_icon(self, "icon3", self.icons.icon3_inactive)
        }
        else
        //Fan is on
        {
            //turn main icon on & display speed selector
            self.set_icon(self, "icon", self.icons.icon_active)
            self.set_field(self, "icon_style", self.css.icon_style_active)

            //decide which icon to mark as selected
            // Fix: Check for percentage if speed is not present directly (HA Modern Fan)
            var current_speed = state.attributes.speed;
            if (current_speed === undefined && state.attributes.percentage !== undefined) {
                // Map percentage to low/medium/high if possible, or just exact match?
                // The widget expects exact match with fields.low_speed etc.
                current_speed = state.attributes.percentage;
            }

            if (current_speed == self.parameters.fields.low_speed) {
                self.set_field(self, "speed1_style", self.css.speed1_style_active)
                self.set_field(self, "speed2_style", self.css.speed2_style_inactive)
                self.set_field(self, "speed3_style", self.css.speed3_style_inactive)
                self.set_icon(self, "icon1", self.icons.icon1_active)
                self.set_icon(self, "icon2", self.icons.icon2_inactive)
                self.set_icon(self, "icon3", self.icons.icon3_inactive)
            }
            else if (current_speed == self.parameters.fields.medium_speed) {
                self.set_field(self, "speed1_style", self.css.speed1_style_inactive)
                self.set_field(self, "speed2_style", self.css.speed2_style_active)
                self.set_field(self, "speed3_style", self.css.speed3_style_inactive)
                self.set_icon(self, "icon1", self.icons.icon1_inactive)
                self.set_icon(self, "icon2", self.icons.icon2_active)
                self.set_icon(self, "icon3", self.icons.icon3_inactive)
            }
            else if (current_speed == self.parameters.fields.high_speed) {
                self.set_field(self, "speed1_style", self.css.speed1_style_inactive)
                self.set_field(self, "speed2_style", self.css.speed2_style_inactive)
                self.set_field(self, "speed3_style", self.css.speed3_style_active)
                self.set_icon(self, "icon1", self.icons.icon1_inactive)
                self.set_icon(self, "icon2", self.icons.icon2_inactive)
                self.set_icon(self, "icon3", self.icons.icon3_active)
            }
            else {
                // Unknown speed
                self.set_field(self, "speed1_style", self.css.speed1_style_inactive)
                self.set_field(self, "speed2_style", self.css.speed2_style_inactive)
                self.set_field(self, "speed3_style", self.css.speed3_style_inactive)
            }
        }
    }

}
