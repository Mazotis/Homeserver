lastupdate = 0
var xhr
var xhrAbortable = false
var hasRoomGroups = false
var modulesToRefresh = new Array()
var dmconfig
var oldstateJSON, stateJSON
var pendingRequests = 0

$(document).ready(function() {
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
});

function abortPendingRequests() {
    if (xhrAbortable) {
        xhr.abort()
    }
    $("#update-spin").hide()
}

function getResult() {
    getConfig()
    $("#preloader").show()
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "getstate",
                isasync: "True"
            },
        success: function(data){
            $("#preloader").hide()
            stateJSON = JSON.parse(decodeURIComponent(data))
            var cnt = 0
            $('#suntime').html(stateJSON.starttime)

            //var ghtml = '<div class="row"><div class="col-sm-3">'
            var ghtml = '<div class="card-columns gcard-columns">'
            for (group in stateJSON.groups) {
                var skip_group = false
                if (stateJSON.roomgroups != "") {
                    hasRoomGroups = true
                    var rgroups = stateJSON.roomgroups.split(",")
                    for (grp in rgroups) {
                        if (rgroups[grp] == stateJSON.groups[group]) {
                            skip_group = true
                        }
                    }
                }

                if (skip_group == false) {
                    $("#groups").html("")
                    $("#groupcardmodel").find(".card-header").text(stateJSON.groups[group].charAt(0).toUpperCase() + stateJSON.groups[group].substr(1).toLowerCase())
                    ghtml += '<div class="gcard noselect-nooverflow" id="gcard' + cnt + '">' + $("#groupcardmodel").html() + '</div>'
                }
                cnt = cnt + 1
            }
            ghtml += '</div>'
            $("#groups").html(ghtml)

            cnt = 0
            //var html = '<div class="row"><div id="update-spin" class="col-12"><center><h5><div class="spinner-border noselect-nooverflow" role="status"></div>&nbsp;Updating device status...</h5></center></div><div class="col-sm-4">'
            var html = '<div class="card-columns dcard-columns">'
            for (_ in stateJSON.state) {
                html += generateCard(cnt, stateJSON)
                cnt = cnt + 1
            }

            $("#cardmodel").remove()

            if (hasRoomGroups) {
                var rhtml = ''
                var rgroups = stateJSON.roomgroups.split(",")

                $("#rooms-section").show()
                for (cnt in rgroups) {
                    rhtml += '<div class="card rcard mb-3 noselect-nooverflow" id="rcard-' + rgroups[cnt] + '"><h4 class="card-header title-header bg-danger text-white" style="font-weight:bold;">' + rgroups[cnt].charAt(0).toUpperCase() + rgroups[cnt].substr(1).toLowerCase() + '</h4><div class="card-body d-body card-columns" style="display:none;"></div><h5 class="card-header bg-danger d-count text-white title-footer"><div style="float:right"><input type="checkbox" class="rcard-toggle" data-onstyle="success" data-offstyle="danger" data-size="sm"></div></h5></div>'
                }

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
            $("#update-spin").hide()
            getResultRefresh()
        }
    })
}

function getResultRefresh() {
    $("#update-spin").show()

    xhrAbortable = true
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
            lastupdate = new Date()
            var i;
            for (i = 0; i < modulesToRefresh.length; i++) { 
                getContent(modulesToRefresh[i]);
            }
            computeCards()
            $("#update-spin").hide()
        }
    })  
}

function getOneResult() {
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "getstate",
                isasync: "True"
            },
        success: function(data){
            pendingRequests--
            oldstateJSON = stateJSON
            stateJSON = JSON.parse(decodeURIComponent(data))
            lastupdate = new Date()
            if (pendingRequests == 0) {
                computeCards()
            }
        }
    })
}

function generateCard(devid, data, a_this = null) {
    if (a_this != null) {
        card = $(a_this)
    } else {
        card = $("#cardmodel").find("div.mb-3")
    }
    card.attr("cid", devid)
    card.find(".card-title").text(data.name[devid])
    card.find(".text-muted").text(data.type[devid])
    card.find("p.c-desc").text(data.description[devid])

    html = card.parent().html()

    return html
}

function computeCards() {
    $(".card").removeClass("disabledbutton")
    $(".dcard").each(function() {
        var cid, cinit, hascontrols
        cid = parseInt($(this).attr("cid"))
        cinit = $(this).attr("cinit")
        hascontrols = false

        $(this).find(".sliderpick").hide()
        if (["noop"].includes(stateJSON.colortype[cid])) {
            $(this).find(".noop").show()
        } else {
            $(this).find(".card-footer").append('<i class="fas fa-cog text-white cog-btn" onclick="getConfigDevice('+ cid + ')" title="_(Device configuration)"></i>')
            if (stateJSON.locked[cid] == "1") {
                $(this).find(".controls-div").hide()
                $(this).find(".card-footer center").append('<i class="fas fa-lock text-white lock-btn" onclick="setLockDevice(0,' + cid + ')" title="_(Unlock device)"></i>')
            } else {
                $(this).find(".controls-div").show()
                $(this).find(".card-footer center").append('<i class="fas fa-unlock text-white lock-btn" onclick="setLockDevice(1,' + cid + ')" title="_(Lock device in this state)"></i>')
            }

            if (stateJSON.mode[cid] == false) {
                $(this).find(".autobtn").removeClass('active')
                $(this).find(".manbtn").addClass('active')
            } else {
                $(this).find(".autobtn").addClass('active')
                $(this).find(".manbtn").removeClass('active')
            }

            if (stateJSON.op_forceoff[cid] == false) {
                $(this).find(".forceoff").show()
            }

            if (stateJSON.op_ignoremode[cid]) {
                $(this).find(".ignoremode").show()
            }

            if (stateJSON.op_skiptime[cid] == false) {
                $(this).find(".skiptime").show()
            }

            if (stateJSON.op_actiondelay[cid] != "0") {
                $(this).find(".actiondelay").show()
                $(this).find(".actiondelay span").html(stateJSON.op_actiondelay[cid] + " s.")
            }

            if (["argb", "rgb", "255"].includes(stateJSON.colortype[cid])) {
                hascontrols = true
                if (stateJSON.state[cid].length == 6) {
                    $(this).find(".colorpick input").attr("value", "#" + stateJSON.state[cid])
                }
                $(this).find(".colorpick").css("display", "inline-block")
                if (cinit != "1") {
                    $(this).find(".colorpick").on("change", function(ev) {
                        color = ev.currentTarget.firstElementChild.value.substr(1)
                        sendPowerRequest(cid, color)
                    })
                }
            }

            if (["100", "255", "argb", "rgb"].includes(stateJSON.colortype[cid])) {
                hascontrols = true
                $(this).find(".sliderpick").show()
                if (cinit != "1") {
                    var slider = $(this).find(".slider")
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

                    var isDragging = false;
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
                            if (parseInt(sliderVal) == 0) {
                                sendPowerRequest(cid, 1, 1)
                            } else {
                                sendPowerRequest(cid, 0, 1)
                            }
                        }
                    });
                }
            }

            if (!hascontrols && cinit != "1") {   
                $(this).find(".controls-div").prepend('<input type="checkbox" class="dcard-toggle" data-onstyle="success" data-offstyle="danger" data-size="lg">')
            }

            $(this).find(".slider").roundSlider("setValue", parseInt(stateJSON.intensity[cid]))
            var sliderVal = $(this).find(".slider").roundSlider("getValue")
            if (parseInt(sliderVal) == 0) {
                $(this).find(".rs-handle").css("border", "5px solid #dc3545")
            } else {
                $(this).find(".rs-handle").css("border", "5px solid #28a745")
            }

            if (cinit != "1") {
                $(this).find(".radiomode :input").on('change', function() {
                    sendModeRequest(cid, $(this).val())
                })

                $(this).find(".dcard-toggle").bootstrapToggle()
                $(this).find(".dcard-toggle").change(function() {
                    sendPowerRequest(cid, this.checked ? 1 : 0)
                })

                if (stateJSON.deviceroom[cid] != "") {
                    $(this).prependTo($("#rcard-" + stateJSON.deviceroom[cid] + " > .card-body"))
                }
            }
        }

        $(this).find(".card-header").removeClass("bg-danger")
        $(this).find(".card-header").removeClass("bg-warning")
        $(this).find(".card-header").removeClass("bg-success")
        $(this).find(".card-header").removeClass("progress-bar-striped")
        $(this).removeClass("border-danger")
        $(this).removeClass("border-warning")
        $(this).removeClass("border-success")
        $(this).find(".dcard-toggle").bootstrapToggle('enable')
        if (stateJSON.state[cid] == "0" || (!isNaN(stateJSON.state[cid]) && parseInt(stateJSON.state[cid]) == 0) || stateJSON.state[cid] == "*0") {
            if ($(this).find(".dcard-toggle").prop('checked')) {
                $(this).find(".dcard-toggle").bootstrapToggle('off', true)
            }
            $(this).find(".card-header").addClass("bg-danger")
            $(this).addClass("border-danger")
        } else if (stateJSON.state[cid] == "-2") {
            $(this).find(".dcard-toggle").bootstrapToggle('disable')
            $(this).find(".card-header").addClass("bg-warning")
            $(this).addClass("border-warning")
        } else if (stateJSON.state[cid] != "X") {
            if (!$(this).find(".dcard-toggle").prop('checked')) {
                $(this).find(".dcard-toggle").bootstrapToggle('on', true)
            }
            $(this).find(".card-header").addClass("bg-success")
            $(this).addClass("border-success")
        }

        if (stateJSON.state[cid] == "X") {
            $(this).find(".dcard-toggle").bootstrapToggle('disable')
            $(this).find(".card-header").removeClass("text-white")
            $(this).find(".card-header").append('<i class="fas fa-wrench wrench-btn" onclick="reconnectDevice(' + cid + ')" title="_(Attempt device reconnection)"></i>')
        }

        if (stateJSON.state[cid] == "*0" || stateJSON.state[cid] == "*1") {
            $(this).find(".card-header").addClass("progress-bar-striped")
            $(this).find(".card-header").append('<i class="fas fa-check check-btn" onclick="confirmState(' + cid + ',&apos;' + stateJSON.state[cid] + '&apos;)" title="_(Confirm device state)"></i>')
        } else {
            $(this).find(".check-btn").remove()
        }

        if (stateJSON.icon[cid] != "none") {
            $(this).find(".iconi").attr("class", "iconi " + stateJSON.icon[cid])
        }

        $(this).attr("cinit", "1")
    })

    $(".gcard").each(function() {
        var group, cid, cinit
        group = $(this).find("h5.card-header").text()
        cinit = $(this).attr("cinit")
        cid = $(this).attr("id")

        if (cinit != "1") {
            $(this).find(".gcard-toggle").bootstrapToggle()
            $(this).find(".gcard-toggle").change(function() {
                sendGroupPowerRequest(group, this.checked ? 1 : 0, cid)
            })
        }

        $(this).attr("cinit", "1")
    })

    computeRCards()
}

function computeRCards() {
    $(".rcard").each(function() {
        var cinit, cgroup, hasoffdevices, hasondevices
        cinit = $(this).attr("cinit")
        cgroup = $(this).find("h4.card-header").text()
        hasoffdevices = hasondevices = false
        hasdefectdevices = false

        $(this).find(".card").each(function() {
            cid = parseInt($(this).attr("cid"))
            if (parseInt(stateJSON.state[cid]) == 0 || stateJSON.state[cid] == "*0") {
                hasoffdevices = true
            } else {
                hasondevices = true
            }
            if (stateJSON.state[cid] == "X") {
                hasdefectdevices = true
            }
        })

        if (cinit != "1") {
            $(this).find(".title-header").on("click", function() {
                if ($(this).parent().find(".card-body").css("display") == "none") {
                    $("#open-rcard").find(".card-body").hide("fast")
                    $("#open-rcard").children().prependTo(".rcolumns")
                    $(this).parent().prependTo("#open-rcard")
                    $(this).parent().find(".card-body").show("fast")
                    $([document.documentElement, document.body]).animate({
                        scrollTop: $(this).offset().top
                    }, 500);
                    $("#open-rcard").find(".title-header").addClass("open-rcard-header")
                    $("#open-rcard").find(".title-footer").addClass("open-rcard-header")
                    $("#open-rcard").find(".d-body").addClass("open-rcard-body")
                    $("#open-rcard").find(".rcard").addClass("open-rcard-card")
                } else {
                    $(this).parent().prependTo(".rcolumns")
                    $(this).parent().find(".card-body").hide("fast")
                }

                $(".rcolumns").find(".title-header").removeClass("open-rcard-header")
                $(".rcolumns").find(".title-footer").removeClass("open-rcard-header")
                $(".rcolumns").find(".d-body").removeClass("open-rcard-body")
                $(".rcolumns").find(".rcard").removeClass("open-rcard-card")
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
        $(this).find(".d-count").removeClass("bg-danger")
        $(this).find(".d-count").removeClass("bg-warning")
        $(this).find(".d-count").removeClass("bg-success")
        $(this).find(".rcard-toggle").bootstrapToggle('enable')
        if (hasoffdevices == false && hasdefectdevices == false) {
            $(this).addClass("border-success")
            $(this).find(".title-header").addClass("bg-success")
            $(this).find(".d-count").addClass("bg-success")
            if (!$(this).find(".rcard-toggle").prop('checked')) {
                $(this).find(".rcard-toggle").bootstrapToggle('on', true)
            }
        } else if (hasondevices == false && hasdefectdevices == false) {
            $(this).addClass("border-danger")
            $(this).find(".title-header").addClass("bg-danger")
            $(this).find(".d-count").addClass("bg-danger")
            if ($(this).find(".rcard-toggle").prop('checked')) {
                $(this).find(".rcard-toggle").bootstrapToggle('off', true)
            }
        } else if (hasdefectdevices == false) {
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
    $(".card[cid=" + devid + "]").addClass("disabledbutton")
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "setstate",
                devid: devid,
                value: value,
                isintensity: is_intensity,
                skiptime: $('input[name=skiptime2]').parent().hasClass("active")
            },
        success: function(data){
            getOneResult()
        }
    })
}

function sendGroupPowerRequest(group, value, devid) {
    abortPendingRequests()
    pendingRequests++
    $("#"+devid).addClass("disabledbutton")
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "setgroup",
                group: group,
                value: value,
                skiptime: $('input[name=skiptime2]').parent().hasClass("active")
            },
        success: function(data){
            getOneResult()
            $("#"+devid).removeClass("disabledbutton")
        }
    })
}

function sendModeRequest(devid, auto) {
    abortPendingRequests()
    pendingRequests++
    $(".card[cid=" + devid + "]").addClass("disabledbutton")
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "setmode",
                mode: auto,
                devid: devid
            },
        success: function(data){
            getOneResult()
        }
    })
}

function sendAllModeAuto() {
    abortPendingRequests()
    pendingRequests++
    $(".dcard").addClass("disabledbutton")
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "setallmode"
            },
        success: function(data){
            getOneResult()
            $(".dcard").removeClass("disabledbutton")
        }
    })
}

function setLockDevice(lock, devid) {
    $("#"+devid).addClass("disabledbutton")
    pendingRequests++
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "setlock",
                lock: lock,
                devid: devid
            },
        success: function(data){
            getOneResult()
        },
        error: function(data){
            console.log(data)
        }
    })    
}

function getContent(amodule, always_refresh = false) {
    if (always_refresh && modulesToRefresh.indexOf(amodule) === -1) {
        modulesToRefresh.push(amodule)
    }
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "getmodule",
                module: amodule
            },
        success: function(data){
            $("#" + amodule + "-content").html(data)
            if (amodule.toUpperCase() in dmconfig) {
                if (amodule == "detector") {
                    $("#" + amodule + "-content").append('<i class="fas fa-cog text-white cog-btn-top" onclick="getConfigModule(&apos;detector&apos;)" title="_(Module configuration)"></i>')
                } else {
                    $("#" + amodule + "-content").parent().parent(".card").find(".card-header").append('<i class="fas fa-cog text-white cog-btn-top" onclick="getConfigModule(&apos;' + amodule + '&apos;)" title="_(Module configuration)"></i>')

                }
            }
        },
        error: function(data){
            console.log(data)
        }
    })
}

function getConfig() {
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "getconfig",
            },
        success: function(data){
            dmconfig = JSON.parse(decodeURIComponent(data))
        },
        error: function(data){
            console.log(data)
        }
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
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "setconfig",
                section: section,
                configdata: encodeURIComponent(JSON.stringify(jsonData))
            },
        success: function(data){
            $("#settingsmodal").find('button').prop("disabled", false)
            $("#settingsmodal").modal('hide')
            setTimeout(function() {
                window.location.reload()
            }, 500)
        },
        error: function(data){
            console.log(data)
        }
    })
}

function reconnectDevice(devid) {
    abortPendingRequests()
    pendingRequests++
    $(".card[cid=" + devid + "]").addClass("disabledbutton")
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "reconnect",
                devid: devid
            },
        success: function(data){
            getOneResult()
        }
    })
}

function confirmState(devid, state) {
    state = state.replace("*", "")
    abortPendingRequests()
    pendingRequests++
    $(".card[cid=" + devid + "]").addClass("disabledbutton")
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "confirmstate",
                state: state,
                devid: devid
            },
        success: function(data){
            getOneResult()
        }
    })    
}


// Javascript ends here. Comment added to prevent EOF bytes loss due to &; characters parsing. TODO - prevent this some other way
