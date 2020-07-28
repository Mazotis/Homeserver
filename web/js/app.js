var lastupdate = 0
var xhr
var xhrAbortable = false
var modulesToRefresh = new Array()
var dmconfig
var oldstateJSON, stateJSON
var pendingRequests = 0
var shownMenu = false

document.addEventListener('DOMContentLoaded', function() {
    getResult();
    lastupdate = new Date()
    window.onscroll = function (e) {
        if ((new Date() - lastupdate) > 20000 ) {
            lastupdate = new Date()
            getResultRefresh()
        }
    }

    $(".hidemode-toggles input:radio").on('change', function() {
        if ($(this).val() == "0") {
            $(".radiomode").css("display", "none")
        } else {
            $(".radiomode").css("display", "inline-flex")
        }
    })

    $("#back-side-menu-btn").on("click", function() {
        if (shownMenu) {
            $("#menu-btn").click()
        }
    })

    $("#menu-btn").on("click", function() {
        if (shownMenu) {
            shownMenu = false
            $("body").removeClass("modal-open")
            $(".modal-backdrop").remove()
            $("body").css("background-color: inherit")
            $("#side-menu").animate( {
                left:-300
            }, 500)
        } else {
            shownMenu = true
            $("body").addClass("modal-open")
            $("body").append('<div class="modal-backdrop fade show"></div>')
            $(".modal-backdrop").on("click", function() {
                $("#menu-btn").click()
            })
            $("body").css("background-color: rgb(238, 238, 238) !important")
            $("#side-menu").animate( {
                left:0
            }, 500)

        }
    })
});

async function post_webserver(data, callback) {
    let initial_data = {
        request: 'True'
    };
    initial_data = Object.assign(data, initial_data)
    const options = {
        method: 'POST',
        headers: {
            'Content-Type': 'text'
        },
        body: Object.entries(initial_data).map(([key, value]) => `${key}=${encodeURIComponent(value)}`).join("&")
    };

    const response = await fetch('.', options
    ).then(data => data.json()
    ).then(response => {
        callback(response);
    }).catch(error => {
        console.log(error);
        enableElement(".dcard")
    });
}

function showLoading() {
    $(".fa-bars").css("display", "none");
    document.getElementById("update-spin").style.display = "inherit"
}

function hideLoading() {
    $(".fa-bars").css("display", "inherit");
    document.getElementById("update-spin").style.display = "none"
}

function enableElement(element) {
    [].forEach.call(document.querySelectorAll(element + " .card-body"), function(el) {
        el.classList.remove("disabledbutton")
        let ell = el.parentElement.querySelector(".card-loader")
        if (ell != null) {
            ell.style.display = "none"
        }
    })
}

function disableElement(element) {
    [].forEach.call(document.querySelectorAll(element + " .card-body"), function(el) {
        el.classList.add("disabledbutton")
        let ell = el.parentElement.querySelector(".card-loader")
        if (ell != null) {
            ell.style.display = "block"
            ell.style.marginLeft = `${Math.round((el.parentElement.offsetWidth/2)-60)}px`
            ell.style.marginTop = `${Math.round((el.parentElement.offsetHeight/2)-60)}px`
        }
    })
}

function drawTimeBar() {
    const maxTime = 1440

    //Convert hours to 0-1 value, with longer daytime correction
    const cF = (x) => -0.5*Math.cos(2*3.14159*x/48)+0.5

    let actualTime = new Date()
    let actualTimeinMins = actualTime.getHours()*60 + actualTime.getMinutes()

    let sunBallPosition = Math.round(cF(actualTimeinMins/maxTime*24)*100)
    document.getElementById("sun-time-ball").style.left = `${(sunBallPosition)}%`
    document.getElementById("sun-time-ball-line").style.left = `${(sunBallPosition)}%`

    const sunsetTimeinMins = parseInt(stateJSON.sunset.substring(0,2))*60 + parseInt(stateJSON.sunset.substring(3,5))
    const sunsetPosition = Math.round(cF(sunsetTimeinMins/maxTime*24)*100)

    const sunriseTimeInMins = parseInt(stateJSON.sunrise.substring(0,2))*60 + parseInt(stateJSON.sunrise.substring(3,5))
    const sunrisePosition = Math.round(cF(sunriseTimeInMins/maxTime*24)*100)

    document.getElementById("night-time-bar").style.backgroundImage = `linear-gradient(to right, #444 ${sunrisePosition-5}% , transparent ${sunrisePosition}%, transparent ${sunsetPosition-5}%, #444 ${sunsetPosition}%)`
    $("#sun-time-ball").tooltip('hide').attr('data-original-title', `<p style="font-weight:bold;">Last updated at</p><h2>${actualTime.toLocaleTimeString().substring(0,5)}</h2><br>Sunrise time today: <span style="font-weight:bold;">${stateJSON.sunrise.substring(0,5)}</span><br>Sunset time today: <span style="font-weight:bold;">${stateJSON.sunset.substring(0,5)}</span>`);
    $("#sun-time-ball").tooltip('show')
    setTimeout(() => {
        $("#sun-time-ball").tooltip('hide')
    }, 2000)

    if (actualTimeinMins > sunsetTimeinMins || actualTimeinMins < sunriseTimeInMins) {
        document.getElementById("sun-time-ball").style.backgroundColor = '#CDC9C3'
        document.getElementById("sun-time-ball").style.filter = 'blur(1px)'
    } else {
        document.getElementById("sun-time-ball").style.backgroundColor = '#F3B562'
        document.getElementById("sun-time-ball").style.filter = 'blur(4px)'        
    }

    const startTimeinMins = parseInt(stateJSON.starttime.substring(0,2))*60 + parseInt(stateJSON.starttime.substring(3,5))
    const startTimePosition = Math.round(cF(startTimeinMins/maxTime*24)*100)
    const endTimeInMins = parseInt(stateJSON.endtime.substring(0,2))*60 + parseInt(stateJSON.endtime.substring(3,5))
    const endTimePosition = Math.round(cF(endTimeInMins/maxTime*24)*100)

    $("#on-time-bar").tooltip({title:`<p style="font-weight:bold;">Time check feature</p>No limitations between <span style="font-weight:bold;">${stateJSON.sunset.substring(0,5)}</span> and <span style="font-weight:bold;">${stateJSON.endtime.substring(0,5)}</span>`})
    $("#off-time-bar").tooltip({title: `<p style="font-weight:bold;">Time check feature</p>No limitations between <span style="font-weight:bold;">${stateJSON.sunset.substring(0,5)}</span> and <span style="font-weight:bold;">${stateJSON.endtime.substring(0,5)}</span>`})
    if (startTimeinMins <= endTimeInMins) {
        const barwidth = endTimePosition - startTimeinMins
        document.getElementById("off-time-bar").style.width = `100%`
        document.getElementById("off-time-bar").style.display = `block`
        document.getElementById("off-time-bar").style.zIndex = `9003`
        document.getElementById("on-time-bar").style.left = `${startTimePosition}%`
        document.getElementById("on-time-bar").style.width = `${Math.round(barwidth)}%`
        document.getElementById("on-time-bar").style.display = `block`
        document.getElementById("on-time-bar").style.zIndex = `9004`
    } else {
        const barwidth = startTimeinMins - endTimePosition
        document.getElementById("on-time-bar").style.width = `100%`
        document.getElementById("on-time-bar").style.display = `block`
        document.getElementById("on-time-bar").style.zIndex = `9003`
        document.getElementById("off-time-bar").style.left = `${endTimePosition}%`
        document.getElementById("off-time-bar").style.width = `${Math.round(barwidth)}%`
        document.getElementById("off-time-bar").style.display = `block`
        document.getElementById("off-time-bar").style.zIndex = `9004`
    }

    /*
    const detectorsunsetTimeinMins = parseInt(stateJSON.detectorstart.substring(0,2))*60 + parseInt(stateJSON.detectorstart.substring(3,5))
    const detectorStartPosition = Math.round(cF(detectorsunsetTimeinMins/maxTime*24)*100)

    const detectorEndTimeInMins = parseInt(stateJSON.detectorend.substring(0,2))*60 + parseInt(stateJSON.detectorend.substring(3,5))
    const detectorEndPosition = Math.round(cF(detectorEndTimeInMins/maxTime*24)*100)

    $("#on-detector-bar").tooltip({title: `Device detector active between <span style="font-weight:bold;">${stateJSON.detectorstart}</span> and <span style="font-weight:bold;">${stateJSON.detectorend}</span>`})
    $("#off-detector-bar").tooltip({title: `Device detector active between <span style="font-weight:bold;">${stateJSON.detectorstart}</span> and <span style="font-weight:bold;">${stateJSON.detectorend}</span>`})
    if (detectorsunsetTimeinMins <= detectorEndTimeInMins) {
        const barwidth = detectorEndPosition - detectorStartPosition
        document.getElementById("off-detector-bar").style.width = `100%`
        document.getElementById("off-detector-bar").style.display = `block`
        document.getElementById("off-detector-bar").style.zIndex = `9003`
        document.getElementById("on-detector-bar").style.left = `${detectorStartPosition}%`
        document.getElementById("on-detector-bar").style.width = `${Math.round(barwidth)}%`
        document.getElementById("on-detector-bar").style.display = `block`
        document.getElementById("on-detector-bar").style.zIndex = `9004`
    } else {
        const barwidth = detectorStartPosition - detectorEndPosition
        document.getElementById("on-detector-bar").style.width = `100%`
        document.getElementById("on-detector-bar").style.display = `block`
        document.getElementById("on-detector-bar").style.zIndex = `9003`
        document.getElementById("off-detector-bar").style.left = `${detectorEndPosition}%`
        document.getElementById("off-detector-bar").style.width = `${Math.round(barwidth)}%`
        document.getElementById("off-detector-bar").style.display = `block`
        document.getElementById("off-detector-bar").style.zIndex = `9004`
    }
    */
}

function abortPendingRequests() {
    if (xhrAbortable) {
        xhr.abort()
    }
    hideLoading()
}

async function getResult() {
    getConfig()
    showLoading()

    const req_data = {
        reqtype: "getstate",
        isasync: "True"
    };

    await post_webserver(req_data, (data) => {
        stateJSON = data
        //console.log(stateJSON)
        if (stateJSON.sunrise != false && stateJSON.sunset != false) {
            drawTimeBar();
        } else {
            $("#time-bar").hide()
            $("#btn-bar").css("width", "100%")
        }
        let cnt = 0
        $('#suntime').html(stateJSON.sunset)
        $("#version-span").html(stateJSON.version)

        let ghtml = '<div class="card-columns gcard-columns">'
        for (group in stateJSON.groups) {
            ghtml += generateCardForGroup(group, cnt)
            cnt = cnt + 1
        }
        ghtml += '</div>'
        $("#groups").html(ghtml)

        cnt = 0
        var html = '<div class="card-columns dcard-columns">'
        for (_ in stateJSON.state) {
            html += '<div id="dcard' + cnt + '"></div>'
            cnt = cnt + 1
        }

        html += generateBlankCard()

        if (stateJSON.roomgroups != "") {
            var rhtml = ''
            var rgroups = stateJSON.roomgroups.split(",")

            $("#rooms-section").show()
            for (cnt in rgroups) {
                rhtml += generateRoomForGroup(rgroups[cnt])
            }

            rhtml += generateBlankRoom()
            $(".rcolumns").html(rhtml)
        }

        html += '</div></div><hr>'

        for (_mod in stateJSON.moduleweb) {
            if (stateJSON.moduleweb[_mod] != "none") {
                if (stateJSON.moduleweb[_mod] == "detector.html") {
                    $.get("/modules/" + stateJSON.moduleweb[_mod], function(htmlpage) {
                        $("#detector-module-location").append(htmlpage)
                    });
                } else {
                    $.get("/modules/" + stateJSON.moduleweb[_mod], function(htmlpage) {
                        $("#modulesid").append(htmlpage)
                    });
                }
            }
        }

        $("#resultid").html(html)
        computeCards()
        hideLoading()
        getResultRefresh()
    })
}

function getResultRefresh() {
    showLoading()

    xhrAbortable = true
    //TODO Remove ajax but keep cancellable request
    xhr = $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "getstate",
                isasync: "False"
            },
        success: function(data){
            xhrAbortable = false
            oldstateJSON = stateJSON
            stateJSON = JSON.parse(decodeURIComponent(data))
            if (stateJSON.sunrise != false && stateJSON.sunset != false) {
                drawTimeBar();
            }
            lastupdate = new Date()
            var i;
            for (i = 0; i < modulesToRefresh.length; i++) { 
                getContent(modulesToRefresh[i]);
            }
            computeCards()
            hideLoading()
        }
    })  
}

function getDeviceResult(devid) {
    const req_data = {
        reqtype: "getstate",
        isasync: "False",
        devid: devid
    }

    post_webserver(req_data, (data) => {
        $(".dcard").each(function() {
            $(this).attr("needsync", "0")
        });
        pendingRequests--
        oldstateJSON = stateJSON
        stateJSON = data
        lastupdate = new Date()
        computeCards()
    })
}

function getAllResults() {
    const req_data = {
        reqtype: "getstate",
        isasync: "True"
    }

    post_webserver(req_data, (data) => {
        pendingRequests--
        oldstateJSON = stateJSON
        stateJSON = data
        //console.log(stateJSON)
        lastupdate = new Date()
        computeCards()
    })
}

function closeTooltips() {
    $("div[data-toggle='tooltip']").each(function() {
        $(this).tooltip('hide');
    });
}

function enableHistoryTooltips() {
    $("span[class='historytooltip']").each(function() {
        $(this).tooltip({
            container: 'body',
            template: '<div class="tooltip" role="tooltip"><div class="arrow"></div><div class="tooltip-inner" style="max-width:500px !important"></div></div>'
        });
    });
}

function getJSONForId(device_id, state_json) {
    if (state_json != null) {
        cardJSON = new Object;
        Object.entries(state_json).map(([key, value]) => {
            const non_device_prop = ['roomgroups', 'sunset', 'sunrise', 'version'];
            if (!non_device_prop.includes(key)) {
                cardJSON[key] = value[device_id]
            }
        });

        return cardJSON
    }

    return false
}

function jsonEqual(a,b) {
    if (a === false || b === false) {
        return false
    }
    let jsonequals = JSON.stringify(a) === JSON.stringify(b)
    return jsonequals;
}

function generateCardForGroup(group, position) {
    let skip_group = false
    let html = ""
    if (stateJSON.roomgroups != "") {
        let rgroups = stateJSON.roomgroups.split(",")
        for (grp in rgroups) {
            if (rgroups[grp] == stateJSON.groups[group]) {
                skip_group = true
            }
        }
    }

    if (skip_group == false) {
        let title = stateJSON.groups[group].charAt(0).toUpperCase() + stateJSON.groups[group].substr(1).toLowerCase()
        html = `
<div class="gcard noselect-nooverflow" id="gcard${position}">
    <div id="groupcardmodel">
        <div class="card text-center bg-light mb-3">
            <h5 class="card-header " style="font-weight:bold;">${title}</h5>
            <div style="padding:5px;">
                <center>
                    <input type="checkbox" class="gcard-toggle" data-onstyle="success" data-offstyle="danger">
                </center>
            </div>
        </div>
    </div>
</div>`
    }

    return html
}

function generateRoomForGroup(room) {
    let title = room.charAt(0).toUpperCase() + room.substr(1).toLowerCase()
    return `
    <div class="card rcard mb-3 noselect-nooverflow" id="rcard-${room.replace(/\s/g, '')}">
        <h4 class="card-header title-header bg-danger text-white" style="font-weight:bold;">${title}</h4>
        <div class="card-body d-body card-columns" style="display:none;">
        </div>
        <h5 class="card-header bg-danger d-count text-white title-footer">
            <div style="float:right">
                <input type="checkbox" class="rcard-toggle" data-onstyle="success" data-offstyle="danger" data-size="sm">
            </div>
        </h5>
    </div>
    `
}

function generateCardForId(device_id) {
    let cardJSON = getJSONForId(device_id, stateJSON)

    let cardhtml = $(`
<div id="cardmodel" style="display:none;">
    <div class="dcard card text-center mb-3" cid="${device_id}">
        <div class="card-loader" style="display:none;"></div>
        <div class="card-header text-white" style="padding:5px;min-height: 30px;">
            <span class="historytooltip" style="float:right" data-placement="right" data-toggle="tooltip" data-html="true" data-title="N/A"><i class="fas fa-history"></i>&nbsp;</span>
            <center>
                <i class="iconi"></i>
            </center>
        </div>
        <div class="card-body " style="padding-top:0; padding:0.25rem;">
            <h5 class="card-title " style="font-weight:bold;margin-top:0.75rem; margin-bottom:0;">${cardJSON.name}</h5>
            <small class="text-muted ">${cardJSON.type}</small>
            <p class="card-text c-desc">${cardJSON.description}</p>
            <div class="controls-div">
                <div>
                    <center>
                        <div class="colorpick">
                            <input type="color" cid="" style="width:200%; height:200%; transform: translate(-25%, -25%);">
                        </div>
                        <span class="sliderpick">
                            <div class="slider"></div>
                        </span>
                    </center>
                </div>
                <div class="btn-group btn-group-sm btn-group-toggle radiomode" data-toggle="buttons" style="display:none;margin-top:5px;">
                    <label class="btn btn-secondary autobtn" ><input type="radio" name="auto" value="true" autocomplete="off"> <tl>Auto</tl></label>
                    <label class="btn btn-secondary manbtn"><input type="radio" name="man" value="false" autocomplete="off"> <tl>Manual</tl></label>
                </div>
            </div>
        </div>
        <div class="card-footer ">
            <center>&nbsp;
                <i class="fas fa-clock skiptime" title="_(Device follows the time-check feature)" style="margin-right:5px; display:none"></i>
                <i class="fas fa-power-off forceoff" title="_(If the device status is OFF, will ignore all turn-off requests)" style="margin-right:5px; display:none"></i>
                <i class="fas fa-exclamation ignoremode" title="_(Device ignores its mode)" style="display:none"></i>
                <span class="badge badge-secondary actiondelay" title="_(Device has a delay between state changes)" style="display:none"><span></span>&nbsp;<i class="fas fa-hourglass-half"></i></span>
                <i class="fas fa-stop-circle noop" title="_(Device is read-only)" style="display:none;"></i>
            &nbsp;</center>
        </div>
    </div>
</div>
    `)

    let hascontrols = false

    $(cardhtml).find(".sliderpick").hide()
    if (cardJSON.colortype === "noop") {
        $(cardhtml).find(".noop").show()
    } else {
        $(cardhtml).find(".card-footer").append(`<i class="fas fa-cog text-white cog-btn" onclick="getConfigDevice(${device_id})" title="_(Device configuration)"></i>`)
        if (cardJSON.locked === "1") {
            $(cardhtml).find(".controls-div").hide()
            $(cardhtml).find(".card-footer center").append(`<i class="fas fa-lock text-white lock-btn" onclick="setLockDevice(0,${device_id})" title="_(Unlock device)"></i>`)
        } else {
            $(cardhtml).find(".controls-div").show()
            $(cardhtml).find(".card-footer center").append(`<i class="fas fa-unlock text-white lock-btn" onclick="setLockDevice(1,${device_id})" title="_(Lock device in this state)"></i>`)
        }

        if (cardJSON.mode === false) {
            $(cardhtml).find(".autobtn").removeClass('active')
            $(cardhtml).find(".manbtn").addClass('active')
        } else {
            $(cardhtml).find(".autobtn").addClass('active')
            $(cardhtml).find(".manbtn").removeClass('active')
        }

        if (cardJSON.op_forceoff === false) {
            $(cardhtml).find(".forceoff").show()
        }

        if (cardJSON.op_ignoremode) {
            $(cardhtml).find(".ignoremode").show()
        }

        if (cardJSON.op_skiptime === true) {
            $(cardhtml).find(".skiptime").show()
        }

        if (cardJSON.op_actiondelay != "0") {
            $(cardhtml).find(".actiondelay").show()
            $(cardhtml).find(".actiondelay span").html(cardJSON.op_actiondelay + " s.")
        }

        if (["argb", "rgb", "255"].includes(cardJSON.colortype)) {
            hascontrols = true
            if (cardJSON.state.length == 6) {
                $(cardhtml).find(".colorpick input").attr("value", "#" + cardJSON.state)
            }
            $(cardhtml).find(".colorpick").css("display", "inline-block")
        }

        if (["100", "255", "argb", "rgb"].includes(cardJSON.colortype)) {
            hascontrols = true
            $(cardhtml).find(".sliderpick").show()
        }

        if (!hascontrols) {   
            $(cardhtml).find(".controls-div").prepend('<input type="checkbox" class="dcard-toggle" data-onstyle="success" data-offstyle="danger" data-size="lg">')
        } else {
            $(cardhtml).find(".controls-div").append('<input type="checkbox" class="dcard-toggle" data-onstyle="success" data-offstyle="danger" data-size="sm">')
        }
    }

    if (cardJSON.state === "0" || (!isNaN(cardJSON.state) && parseInt(cardJSON.state) === 0) || cardJSON.state === "*0") {
        if ($(cardhtml).find(".dcard-toggle").prop('checked')) {
            $(cardhtml).find(".dcard-toggle").prop('checked', false)
        } 
        $(cardhtml).find(".card-header").addClass("bg-danger")
        $(cardhtml).addClass("border-danger")
    } else if (cardJSON.state === "-2") {
        $(cardhtml).find(".dcard-toggle").bootstrapToggle('disable')
        $(cardhtml).find(".card-header").addClass("bg-warning")
        $(cardhtml).addClass("border-warning")
    } else if (cardJSON.state != "X") {
        if (!$(cardhtml).find(".dcard-toggle").prop('checked')) {
            $(cardhtml).find(".dcard-toggle").prop('checked', true)
        }
        $(cardhtml).find(".card-header").addClass("bg-success")
        $(cardhtml).addClass("border-success")
    }

    if (cardJSON.state === "X") {
        $(cardhtml).find(".dcard-toggle").bootstrapToggle('disable')
        $(cardhtml).find(".card-header").removeClass("text-white")
        $(cardhtml).find(".card-header").append(`<i class="fas fa-wrench wrench-btn" onclick="reconnectDevice(${device_id})" title="_(Attempt device reconnection)"></i>`)
    }

    if (cardJSON.state === "*0" || cardJSON.state === "*1") {
        $(cardhtml).find(".card-header").addClass("progress-bar-striped")
        $(cardhtml).find(".card-header").append(`<i class="fas fa-check check-btn" onclick="confirmState(${device_id},'${cardJSON.state}')" title="_(Confirm device state)"></i>`)
    } else {
        $(cardhtml).find(".check-btn").remove()
    }

    if (cardJSON.icon != "none") {
        $(cardhtml).find(".iconi").attr("class", "iconi " + cardJSON.icon)
        $(cardhtml).find(".iconi").css("margin-left", "16px")
    }

    return $(cardhtml).html()
}

function generateBlankCard() {
    return `
<div id="cardmodel">
    <div class="card text-center mb-3 bg-secondary new-dev-card">
        <div class="card-body text-white" style="padding-top:0; padding:0.25rem;">
            <h5 class="card-title" style="margin-top:0.75rem;"><i class='fas fa-plus-circle'></i> Add device (WIP)</h5>
         </div>
    </div>
</div>
    `
}

function generateBlankRoom() {
    return `
<div class="card mb-3 noselect-nooverflow" onclick="getGroupSelect()">
    <h5 class="card-header title-header bg-secondary text-white new-dev-card">
        <i class="fas fa-plus-circle"></i> _(Add/remove room groups)
    </h5>
</div>`
}

function computeCards() {
    enableElement(".card")

    let cnt = 0
    for (_ in stateJSON.state) {
        if (!jsonEqual(getJSONForId(cnt, stateJSON),getJSONForId(cnt, oldstateJSON)) || $(".dcard[cid='" + cnt + "']").attr("needsredraw") == "1") {
            $(".dcard[cid='" + cnt + "']").remove()
            if ($(".dcard[cid='" + cnt + "']").attr("needsync") != "1") {
                $("#dcard" + cnt).html(generateCardForId(cnt))
            }
        }
        cnt = cnt + 1
    }

    $(".dcard").each(function() {
        let cid = parseInt($(this).attr("cid"))

        if ($(this).attr("cloned") != "1") {
            if (stateJSON.deviceroom[cid] != "") {
                rgroups = stateJSON.deviceroom[cid].split(",")
                for (_cnt in rgroups) {
                    let clone = $(this).clone(true)
                    let position = 9999
                    clone.attr("cloned", "1")
                    $("#rcard-" + rgroups[_cnt].replace(/\s/g, '')).find(".dcard").each(function() {
                        let thisCid = parseInt($(this).attr("cid")) 
                        if (position > thisCid && thisCid > cid) {
                            position = thisCid
                        }
                    })

                    if (position != 9999) {
                        clone.insertBefore($("#rcard-" + rgroups[_cnt].replace(/\s/g, '') + " .dcard[cid='" + position + "']"))
                    } else {
                        clone.appendTo($("#rcard-" + rgroups[_cnt].replace(/\s/g, '') + " > .card-body"))
                    }
                }
                $(this).remove()
            }
        }
    });

    $(".dcard").each(function() {
        let cid = parseInt($(this).attr("cid"))

        if ($(this).attr("events") != "1") {
            $(this).find(".colorpick").on("change", function(ev) {
                color = ev.currentTarget.firstElementChild.value.substr(1)
                $(this).attr("needsync", "1")
                sendPowerRequest(cid, color)
            })

            let slider = $(this).find(".slider")
            slider.roundSlider({
                sliderType: "min-range",
                handleShape: "round",
                width: 30,
                radius: 70,
                value: parseInt(stateJSON.intensity[cid]),
                editableTooltip: false,
                change: function(event) {
                    sendPowerRequest(cid, event.value, 1)
                }
            });

            if (parseInt(stateJSON.intensity[cid]) == 0) {
                //Workaround roundslider not calculating proper margins for tooltips at first launch
                slider.find(".rs-tooltip").css("margin-top", "-10px")
                slider.find(".rs-tooltip").css("margin-left", "-5px")
            } else {
                //Workaround roundslider not calculating proper margins for tooltips at first launch
                slider.find(".rs-tooltip").css("margin-top", "-10px")
                slider.find(".rs-tooltip").css("margin-left", "-10px")                
            }

            let isDragging = false;
            $(this).find(".rs-handle").mousedown(function() {
                $(window).mousemove(function() {
                    isDragging = true;
                    $(window).unbind("mousemove");
                });
            }).mouseup(function() {
                var wasDragging = isDragging;
                isDragging = false;
                $(window).unbind("mousemove");
                if (!wasDragging) {
                    var sliderVal = slider.roundSlider("getValue")
                    $(this).attr("needsync", "1")
                    if (parseInt(sliderVal) == 0) {
                        sendPowerRequest(cid, 1, 1)
                    } else {
                        sendPowerRequest(cid, 0, 1)
                    }
                }
            });

            if (stateJSON.history[cid] != "") {
                history = stateJSON.history[cid].join("<br>")
                $(this).find(".historytooltip").attr("data-title", stateJSON.history[cid].join("<br>"))
            }

            var sliderVal = $(this).find(".slider").roundSlider("getValue")
            if (parseInt(sliderVal) == 0) {
                $(this).find(".rs-handle").css("border", "5px solid #dc3545")
            } else {
                $(this).find(".rs-handle").css("border", "5px solid #28a745")
            }

            $(this).find(".radiomode :input").on('change', function() {
                sendModeRequest(cid, $(this).val())
            })

            $(this).find(".dcard-toggle").bootstrapToggle()
            if (stateJSON.state[cid] === "0" || (!isNaN(stateJSON.state[cid]) && parseInt(stateJSON.state[cid]) === 0) || stateJSON.state[cid] === "*0") {
                if ($(this).find(".dcard-toggle").prop('checked')) {
                    $(this).find(".dcard-toggle").bootstrapToggle('off', false)
                }
            } else if (stateJSON.state[cid] === "-2" || stateJSON.state[cid] === "X") {
                $(this).find(".dcard-toggle").bootstrapToggle('disable')
            } else if (stateJSON.state[cid] != "X") {
                if (!$(this).find(".dcard-toggle").prop('checked')) {
                    $(this).find(".dcard-toggle").bootstrapToggle('on', false)
                }
            }
            $(this).find(".dcard-toggle").change(function() {
                $(this).attr("needsync", "1")
                sendPowerRequest(cid, this.checked ? 1 : 0)
            })

            $(this).attr("events", "1")
        }
    })

    $(".gcard").each(function() {
        var cgroup, cid, cinit, cindex, cgstate
        cgroup = $(this).find("h5.card-header").text()
        cinit = $(this).attr("cinit")
        cid = $(this).attr("id")
        cindex = stateJSON['groups'].indexOf(cgroup.toLowerCase())
        cgstate = stateJSON['groupstates'][cindex]

        if (cinit != "1") {
            $(this).find(".gcard-toggle").bootstrapToggle({width:"100px"})
            $(this).find(".gcard-toggle").change(function() {
                sendGroupPowerRequest(group, this.checked ? 1 : 0, cid)
            })
        }

        $(this).find(".card-header").removeClass("bg-success")
        $(this).find(".card-header").removeClass("bg-warning")
        $(this).find(".card-header").removeClass("bg-danger")
        $(this).find(".card-header").removeClass("text-white")
        $(this).find(".gcard-toggle").bootstrapToggle('off', true)
        if (cgstate == "2") {
            $(this).find(".card-header").addClass("bg-success")
            $(this).find(".gcard-toggle").bootstrapToggle('on', true)
        } else if  (cgstate == "1") {
            $(this).find(".card-header").addClass("bg-warning")
        } else if (cgstate == "0") {
            $(this).find(".card-header").addClass("bg-danger")
            $(this).find(".card-header").addClass("text-white")
        }

        $(this).attr("cinit", "1")
    })

    computeRCards()
    enableHistoryTooltips()
}

var hasOpenRcard = false
function computeRCards() {
    $(".rcard").each(function() {
        var cinit, cgroup, cindex, cgstate
        cinit = $(this).attr("cinit")
        cgroup = $(this).find("h4.card-header").text()
        cindex = stateJSON['groups'].indexOf(cgroup.toLowerCase())
        cgstate = stateJSON['groupstates'][cindex]

        if (cinit != "1") {
            $(this).find(".title-header").on("click", function() {
                closeTooltips()
                if ($(this).parent().find(".card-body").css("display") == "none") {
                    if (hasOpenRcard) {
                        $("#open-rcard").find(".card-body").hide()
                    } else {
                        $("#open-rcard").find(".card-body").fadeOut("fast")
                    }
                    $("#open-rcard").children().prependTo(".rcolumns")
                    $(this).parent().prependTo("#open-rcard")
                    $("#open-rcard").find(".title-header").addClass("open-rcard-header")
                    $("#open-rcard").find(".title-footer").addClass("open-rcard-header")
                    $("#open-rcard").find(".rcard").addClass("open-rcard-card")
                    if (hasOpenRcard) {
                        $(this).parent().find(".card-body").show()
                    } else {
                        $(this).parent().find(".card-body").fadeIn("fast")
                    }
                    hasOpenRcard = true
                    $([document.documentElement, document.body]).animate({
                        scrollTop: $(this).offset().top-55
                    }, 400);
                } else {
                    $(this).parent().find(".card-body").fadeOut("fast", () => {
                        $(this).parent().prependTo(".rcolumns")
                    })
                    hasOpenRcard = false
                }

                setTimeout(() => {
                    $(".rcolumns").find(".title-header").removeClass("open-rcard-header")
                    $(".rcolumns").find(".title-footer").removeClass("open-rcard-header")
                    $(".rcolumns").find(".d-body").removeClass("open-rcard-body")
                    $(".rcolumns").find(".rcard").removeClass("open-rcard-card")
                }, 300)
            })

            var devlen = $(this).find(".card").length
            if (devlen in [0, 1]) {
                $(this).find(".d-count").prepend(devlen + " _(device)")
            } else {
                $(this).find(".d-count").prepend(devlen + " _(devices)")
            }

            $(this).find(".rcard-toggle").bootstrapToggle({
                width: "60px"
            })
            $(this).find(".rcard-toggle").change(function() {
                sendGroupPowerRequest(cgroup, this.checked ? 1 : 0, "rcard-" + cgroup.toLowerCase())
            })
        }

        $(this).removeClass("border-danger")
        $(this).removeClass("border-warning")
        $(this).removeClass("border-success")
        $(this).find(".title-header").removeClass("bg-danger")
        $(this).find(".title-header").removeClass("bg-warning")
        $(this).find(".title-header").removeClass("bg-success")
        $(this).find(".title-header").addClass("text-white")
        $(this).find(".title-footer").addClass("text-white")
        $(this).find(".d-count").removeClass("bg-danger")
        $(this).find(".d-count").removeClass("bg-warning")
        $(this).find(".d-count").removeClass("bg-success")
        $(this).find(".rcard-toggle").bootstrapToggle('enable')
        if (cgstate == "2") {
            $(this).addClass("border-success")
            $(this).find(".title-header").addClass("bg-success")
            $(this).find(".d-count").addClass("bg-success")
            if (!$(this).find(".rcard-toggle").prop('checked')) {
                $(this).find(".rcard-toggle").bootstrapToggle('on', true)
            }
        } else if (cgstate == "0") {
            $(this).addClass("border-danger")
            $(this).find(".title-header").addClass("bg-danger")
            $(this).find(".d-count").addClass("bg-danger")
            if ($(this).find(".rcard-toggle").prop('checked')) {
                $(this).find(".rcard-toggle").bootstrapToggle('off', true)
            }
        } else if (cgstate == "1") {
            $(this).addClass("border-warning")
            $(this).find(".title-header").addClass("bg-warning")
            $(this).find(".d-count").addClass("bg-warning")
            if ($(this).find(".rcard-toggle").prop('checked')) {
                $(this).find(".rcard-toggle").bootstrapToggle('off', true)
            }
        } else {
            $(this).find(".title-header").removeClass("text-white")
            $(this).find(".title-footer").removeClass("text-white")
            $(this).find(".rcard-toggle").bootstrapToggle('disable')
        }

        $(this).attr("cinit", "1")
    })
}

function sendPowerRequest(devid, value, is_intensity=0) {
    abortPendingRequests()
    pendingRequests++
    disableElement(".card[cid='" + devid + "']")
    closeTooltips()
    $(".dcard[cid='" + devid + "']").attr("needsredraw", "1")

    const req_data = {
        reqtype: "setstate",
        devid: devid,
        value: value,
        isintensity: is_intensity
    };

    post_webserver(req_data, (data) => {
        getDeviceResult(devid);
    });
}

function sendGroupPowerRequest(group, value, devid) {
    abortPendingRequests()
    pendingRequests++
    disableElement("#"+devid)
    $("#rcard-" + group.toLowerCase()).find(".rcard-toggle").bootstrapToggle('disable')
    closeTooltips()

    const req_data = {
        reqtype: "setgroup",
        group: encodeURIComponent(group.replace(" ", "_")),
        value: value,
        skiptime: $('input[name=skiptime2]').parent().hasClass("active")
    };

    post_webserver(req_data, (data) => {
        getAllResults(() => {
            $("#rcard-" + group.toLowerCase()).find(".rcard-toggle").bootstrapToggle('enable');
            enableElement("#"+devid);
        });
    });
}

function sendModeRequest(devid, auto) {
    abortPendingRequests()
    pendingRequests++
    disableElement(".card[cid='" + devid + "']")

    const req_data = {
        reqtype: "setmode",
        mode: auto,
        devid: devid
    };

    post_webserver(req_data, (data) => {getDeviceResult(devid);})
}

function sendAllModeAuto() {
    abortPendingRequests()
    pendingRequests++
    disableElement(".dcard")

    const req_data = {
        reqtype: "setallmode"
    }

    post_webserver(req_data, (data) => {
        getAllResults(() => {
            enableElement(".dcard");
        });
    });
}

function setLockDevice(lock, devid) {
    disableElement("#"+devid)
    pendingRequests++

    const req_data = {
        reqtype: "setlock",
        lock: lock,
        devid: devid
    }

    post_webserver(req_data, (data) => {
        getDeviceResult(devid);
    })
}

function getContent(amodule, always_refresh = false) {
    if (always_refresh && modulesToRefresh.indexOf(amodule) === -1) {
        modulesToRefresh.push(amodule)
    }

    const req_data = {
        reqtype: "getmodule",
        module: amodule
    }

    post_webserver(req_data, (data) => {
        $("#" + amodule + "-content").html(data)
        if (amodule.toUpperCase() in dmconfig) {
            if (amodule == "detector") {
                $("#" + amodule + "-content").append('<i class="fas fa-cog text-white cog-btn-top" onclick="getConfigModule(&apos;detector&apos;)" title="_(Module configuration)"></i>')
            } else {
                $("#" + amodule + "-content").parent().parent(".card").find(".card-header").append('<i class="fas fa-cog text-white cog-btn-top" onclick="getConfigModule(&apos;' + amodule + '&apos;)" title="_(Module configuration)"></i>')
            }
        }
    })
}

function getConfig() {
    const req_data = {
        reqtype: "getconfig"
    }

    post_webserver(req_data, (data) => {
        dmconfig = data
    })
}

function getConfigDevice(devid) {
    $("#settingsmodal").find(".modal-title").text("_(Settings for device ID) " + devid)
    $("#settingsmodal").find("#savemodal").attr("onclick", "saveConfig('DEVICE" + devid + "')")
    html = '<p class="small">_(_text1)</p><form id="configform" role="form"><fieldset>'
    for (var entry in dmconfig["DEVICE" + devid]) {
        html += '<div class="form-group row"><label for="' + entry + '" class="col-sm-3 col-form-label" style="word-break:break-all;">' + entry + '</label><div class="col-sm-9"><input type="text" class="form-control" name="' + entry + '" value="' + dmconfig["DEVICE" + devid][entry] + '"></div></div>'
    }
    html += "</fieldset></form>"
    $("#settingsmodal").find(".modal-body").html(html)
    $("#settingsmodal").modal('show')
}

function getConfigModule(amodule) {
    $("#settingsmodal").find(".modal-title").text("_(Settings for module): " + amodule)
    $("#settingsmodal").find("#savemodal").attr("onclick", "saveConfig('" + amodule + "')")
    html = '<p class="small">_(_text1)</p><form id="configform" role="form"><fieldset>'
    for (var entry in dmconfig[amodule.toUpperCase()]) {
        html += '<div class="form-group row"><label for="' + entry + '" class="col-sm-3 col-form-label" style="word-break:break-all;">' + entry + '</label><div class="col-sm-9"><input type="text" class="form-control" name="' + entry + '" value="' + dmconfig[amodule.toUpperCase()][entry] + '"></div></div>'
    }
    html += "</fieldset></form>"
    $("#settingsmodal").find(".modal-body").html(html)
    $("#settingsmodal").modal('show')
}

function saveConfig(section) {
    var jsonData = {}
    $.each($("#configform").serializeArray(), function() {
      jsonData[this.name] = this.value;
    });
    $("#settingsmodal").find('button').prop("disabled", true)
    $("#settingsmodal").find('#savemodal').text("...")

    const req_data = {
        reqtype: "setconfig",
        section: section,
        configdata: encodeURIComponent(JSON.stringify(jsonData))
    }

    post_webserver(req_data, (data) => {})

    setTimeout(function() {
        $("#settingsmodal").find('button').prop("disabled", false)
        $("#settingsmodal").modal('hide')
        window.location.reload()
    }, 4000)
}

function reconnectDevice(devid) {
    abortPendingRequests()
    pendingRequests++
    disableElement(".card[cid='" + devid + "']")

    const req_data = {
        reqtype: "reconnect",
        devid: devid
    }

    post_webserver(req_data, (data) => {
        getDeviceResult(devid);
    })
}

function confirmState(devid, state) {
    state = state.replace("*", "")
    abortPendingRequests()
    pendingRequests++
    disableElement(".card[cid='" + devid + "']")

    const req_data = {
        reqtype: "confirmstate",
        state: state,
        devid: devid
    }

    post_webserver(req_data, (data) => {
        getDeviceResult(devid);
    })   
}

function reloadConfig(){
    $("#reload-config-side-btn").html("Please wait...")
    $("#reload-config-side-btn").attr("onclick", "")


    const req_data = {
        reqtype: "reloadconfig"
    }

    post_webserver(req_data, (data) => {})

    setTimeout(function() {
        $("#settingsmodal").find('button').prop("disabled", false)
        $("#settingsmodal").modal('hide')
        window.location.reload()
    }, 4000)
}

function getPresetEditor(){
    $("#menu-btn").click()
    $.ajax({
        type: "GET",
        url: "modules/preseteditor.html",
        dataType: "html",
        success: function(data){
            $("#additional-content").html(data)
            $("#preseteditor").modal('show')
        },
        error: function(data){
            console.log(data)
        }
    })    
}

function getGroupSelect(){
    $.ajax({
        type: "GET",
        url: "modules/groupselect.html",
        dataType: "html",
        success: function(data){
            $("#additional-content").html(data)
            $("#groupselect").modal('show')
        },
        error: function(data){
            console.log(data)
        }
    })    
}

// Javascript ends here. Comment added to prevent EOF bytes loss due to &; characters parsing. TODO - prevent this some other way
