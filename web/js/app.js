lastupdate = 0
var xhr
var runningRequests = 0
var deduceAbortableRequest = false
var hasRoomGroups = false
var modulesToRefresh = new Array()

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
    xhr.abort()
    if (deduceAbortableRequest && runningRequests > 0) {
        runningRequests--
    }
    $("#update-spin").hide()
}

function getResult() {
    runningRequests++
    $("#preloader").show()
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "1"
            },
        success: function(data){
            $("#preloader").hide()
            var thedata = JSON.parse(decodeURIComponent(data))
            var cnt = 0
            $('#suntime').html(thedata.starttime)

            //var ghtml = '<div class="row"><div class="col-sm-3">'
            var ghtml = '<div class="card-columns gcard-columns">'
            for (group in thedata.groups) {
                var skip_group = false
                if (thedata.roomgroups != "") {
                    hasRoomGroups = true
                    var rgroups = thedata.roomgroups.split(",")
                    for (grp in rgroups) {
                        if (rgroups[grp] == thedata.groups[group]) {
                            skip_group = true
                        }
                    }
                }

                if (skip_group == false) {
                    $("#groups").html("")
                    $("#groupcardmodel").find(".card-header").text(thedata.groups[group].charAt(0).toUpperCase() + thedata.groups[group].substr(1).toLowerCase())
                    ghtml += '<div class="gcard noselect-nooverflow" id="gcard' + cnt + '">' + $("#groupcardmodel").html() + '</div>'
                }
                cnt = cnt + 1
            }
            ghtml += '</div>'
            $("#groups").html(ghtml)

            cnt = 0
            //var html = '<div class="row"><div id="update-spin" class="col-12"><center><h5><div class="spinner-border noselect-nooverflow" role="status"></div>&nbsp;Updating device status...</h5></center></div><div class="col-sm-4">'
            var html = '<div class="card-columns dcard-columns">'
            for (_ in thedata.state) {
                html += generateCard(cnt, thedata)
                cnt = cnt + 1
            }

            $("#cardmodel").remove()

            if (hasRoomGroups) {
                var rhtml = ''
                var rgroups = thedata.roomgroups.split(",")

                $("#rooms-section").show()
                for (cnt in rgroups) {
                    rhtml += '<div class="card rcard mb-3 noselect-nooverflow" id="rcard-' + rgroups[cnt] + '"><h4 class="card-header title-header bg-danger text-white" style="font-weight:bold;">' + rgroups[cnt].charAt(0).toUpperCase() + rgroups[cnt].substr(1).toLowerCase() + '</h4><div class="card-body d-body card-columns" style="display:none;"></div><h5 class="card-header bg-danger d-count text-white title-footer"><div class="btn-group btn-group-sm" role="group" style="float:right;"><button type="button" class="btn btn-danger goffbuttons">OFF</button><button type="button" class="btn btn-success gonbuttons">ON</button></div></h5></div>'
                }

                $(".rcolumns").html(rhtml)
            }

            html += '</div></div><hr>'

            for (_mod in thedata.moduleweb) {
                if (thedata.moduleweb[_mod] != "none") {
                    if (thedata.moduleweb[_mod] == "detector.html") {
                        $.get("/modules/" + thedata.moduleweb[_mod], function(htmlpage) {
                            $("#detector-module-location").append(htmlpage)
                        });
                    } else {
                        $.get("/modules/" + thedata.moduleweb[_mod], function(htmlpage) {
                            $("#resultid").append(htmlpage)
                        });
                    }
                }
            }

            $("#resultid").html(html)
            computeCards()
            getResultPost()
        }
    })
}

function getResultRefresh() {
    runningRequests++
    $("#spin-text").html("Running requests and getting cached state status...")
    $("#update-spin").show()
    deduceAbortableRequest = true

    xhr = $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "1"
            },
        success: function(data){
            var thedata = JSON.parse(decodeURIComponent(data))
            has_errors = false
            var i;
            for (i = 0; i < modulesToRefresh.length; i++) { 
                console.log("called getcontent for " + modulesToRefresh[i])
                getContent(modulesToRefresh[i]);
            }
            for (cnt in thedata.state) {
                thedata.mode[cnt] ? mode = 1 : mode = 0
                if ($(".card[cid=" + cnt + "]").attr("cstate") != thedata.state[cnt]) {
                    $(".card[cid=" + cnt + "]").attr("cstate", thedata.state[cnt])
                    has_errors = true
                }
                if ($(".card[cid=" + cnt + "]").attr("cintensity") != thedata.intensity[cnt]) {
                    $(".card[cid=" + cnt + "]").attr("cintensity", thedata.intensity[cnt])
                    has_errors = true
                }
                if ($(".card[cid=" + cnt + "]").attr("cmode") != mode) {
                    $(".card[cid=" + cnt + "]").attr("cmode", mode)
                    has_errors = true
                }
            }
            if (has_errors) {
                computeCards()
            }
            getResultPost()
        }
    })  
}

function getResultPost() {
    if (runningRequests == 1) {
        deduceAbortableRequest = true
        $("#spin-text").html("Querying device state...")
        $("#update-spin").show()
        xhr = $.ajax({
            type: "POST",
            url: ".",
            dataType: "text",
            data: {
                    request: "True",
                    reqtype: "5"
                },
            success: function(data){
                var thedata = JSON.parse(decodeURIComponent(data))
                has_errors = false
                for (cnt in thedata.state) {
                    thedata.mode[cnt] ? mode = 1 : mode = 0
                    if ($(".card[cid=" + cnt + "]").attr("cstate") != thedata.state[cnt]) {
                        $(".card[cid=" + cnt + "]").attr("cstate", thedata.state[cnt])
                        has_errors = true
                    }
                    if ($(".card[cid=" + cnt + "]").attr("cintensity") != thedata.intensity[cnt]) {
                        $(".card[cid=" + cnt + "]").attr("cintensity", thedata.intensity[cnt])
                        has_errors = true
                    }
                    if ($(".card[cid=" + cnt + "]").attr("cmode") != mode) {
                        $(".card[cid=" + cnt + "]").attr("cmode", mode)
                        has_errors = true
                    }
                }
                if (has_errors) {
                    computeCards()
                }
                runningRequests--
                $("#update-spin").hide()
            }
        })
    } else {
        deduceAbortableRequest = false
        runningRequests--
    }  
}

function getOneResult(devid, last_state) {
    runningRequests++
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "1"
            },
        success: function(data){
            var thedata = JSON.parse(decodeURIComponent(data))
            generateCard(devid, thedata, last_state, $(".card[cid=" + devid + "]"))
            computeCards()
            $(".card[cid=" + devid + "]").removeClass("disabledbutton")
            getResultPost()
        }
    })
}

function generateCard(devid, data, last_state = null, a_this = null) {
    var mode
    data.mode[devid] ? mode = 1 : mode = 0
    if (a_this != null) {
        card = $(a_this)
    } else {
        card = $("#cardmodel").find("div.mb-3")
    }
    card.attr("cstate", data.state[devid])
    card.attr("cintensity", data.intensity[devid])
    card.attr("cid", devid)
    card.attr("cmode", mode)
    card.attr("cskiptime", data.op_skiptime[devid])
    card.attr("cforceoff", data.op_forceoff[devid])
    card.attr("cignoremode", data.op_ignoremode[devid])
    card.attr("cactiondelay", data.op_actiondelay[devid])
    card.attr("cicon", data.icon[devid])
    card.attr("ccolortype", data.colortype[devid])
    card.attr("clocked", data.locked[devid])
    card.attr("croom", data.deviceroom[devid])
    card.find(".card-title").text(data.name[devid])
    card.find(".text-muted").text(data.type[devid])
    card.find("p.c-desc").text(data.description[devid])

    html = card.parent().html()

    return html
}

function computeCards() {
    $(".dcard").each(function() {
        var cstate, cintensity, cid, cmode, ccolortype, cinit, clocked, croom
        cinit = $(this).attr("cinit")
        cstate = $(this).attr("cstate")
        cintensity = $(this).attr("cintensity")
        cid = $(this).attr("cid")
        cmode = $(this).attr("cmode")
        cforceoff = $(this).attr("cforceoff")
        cignoremode = $(this).attr("cignoremode")
        cskiptime = $(this).attr("cskiptime")
        cactiondelay = $(this).attr("cactiondelay")
        cicon = $(this).attr("cicon")
        ccolortype = $(this).attr("ccolortype")
        clocked = $(this).attr("clocked")
        croom = $(this).attr("croom")

        $(this).find(".sliderpick").hide()
        $(this).find(".card-header").removeClass("bg-danger")
        $(this).find(".card-header").removeClass("bg-warning")
        $(this).find(".card-header").removeClass("bg-success")
        $(this).removeClass("border-danger")
        $(this).removeClass("border-warning")
        $(this).removeClass("border-success")
        if (cstate == "0" || (!isNaN(cstate) && parseInt(cstate) == 0)) {
            $(this).find(".offbuttons").attr('disabled', true)
            $(this).find(".onbuttons").attr('disabled', false)
            $(this).find(".card-header").addClass("bg-danger")
            $(this).addClass("border-danger")
        } else if (cstate == "-2") {
            $(this).find(".offbuttons").attr('disabled', true)
            $(this).find(".onbuttons").attr('disabled', true)
            $(this).find(".card-header").addClass("bg-warning")
            $(this).addClass("border-warning")
        } else {
            $(this).find(".offbuttons").attr('disabled', false)
            $(this).find(".onbuttons").attr('disabled', true)
            $(this).find(".card-header").addClass("bg-success")
            $(this).addClass("border-success")
        }

        if (["noop"].includes(ccolortype)) {
            $(this).find(".btn-group").hide()
            $(this).find(".noop").show()
        } else {
            if (clocked == "1") {
                $(this).find(".card-body").hide()
                $(this).find(".card-footer center").append('<i class="fas fa-lock text-white lock-btn" onclick="setLockDevice(0,' + cid + ',' + cstate +')" title="Unlock device"></i>')
            } else {
                $(this).find(".card-body").show()
                $(this).find(".card-footer center").append('<i class="fas fa-unlock text-white lock-btn" onclick="setLockDevice(1,' + cid + ',' + cstate +')" title="Lock device in this state"></i>')
            }

            if (cmode == "0") {
                $(this).find(".autobtn").removeClass('active')
                $(this).find(".manbtn").addClass('active')
            } else {
                $(this).find(".autobtn").addClass('active')
                $(this).find(".manbtn").removeClass('active')
            }

            if (cforceoff == "false") {
                $(this).find(".forceoff").show()
            }

            if (cignoremode == "true") {
                $(this).find(".ignoremode").show()
            }

            if (cskiptime == "false") {
                $(this).find(".skiptime").show()
            }

            if (cactiondelay != "0") {
                $(this).find(".actiondelay").show()
                $(this).find(".actiondelay span").html(cactiondelay + " s.")
            }

            if (["argb", "rgb", "255"].includes(ccolortype)) {
                if (cstate.length == 6) {
                    $(this).find(".colorpick input").attr("value", "#" + cstate)
                }
                $(this).find(".colorpick").css("display", "inline-block")
                if (cinit != "1") {
                    $(this).find(".colorpick").on("change", function(ev) {
                        color = ev.currentTarget.firstElementChild.value.substr(1)
                        sendPowerRequest(cid, color, cstate)
                    })
                }
            }

            if (["100", "255", "argb", "rgb"].includes(ccolortype)) {
                $(this).find(".sliderpick").show()
                $(this).find(".btn-group-lg").hide()
                if (cinit != "1") {
                    var slider = $(this).find(".slider")
                    slider.roundSlider({
                        sliderType: "min-range",
                        handleShape: "round",
                        width: 30,
                        radius: 70,
                        value: parseInt(cintensity),
                        editableTooltip: false,
                        change: function(event) {
                            sendPowerRequest(cid, event.value, cstate, 1)
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
                                sendPowerRequest(cid, 1, cstate, 1)
                            } else {
                                sendPowerRequest(cid, 0, cstate, 1)
                            }
                        }
                    });
                }
            }

            $(this).find(".slider").roundSlider("setValue", parseInt(cintensity))
            var sliderVal = $(this).find(".slider").roundSlider("getValue")
            if (parseInt(sliderVal) == 0) {
                $(this).find(".rs-handle").css("border", "5px solid #dc3545")
            } else {
                $(this).find(".rs-handle").css("border", "5px solid #28a745")
            }

            if (cinit != "1") {
                $(this).find(".radiomode :input").on('change', function() {
                    sendModeRequest(cid, cstate, $(this).val())
                })
                $(this).find(".offbuttons").on('click', function() {
                    sendPowerRequest(cid, 0, cstate)
                })
                $(this).find(".onbuttons").on('click', function() {
                    sendPowerRequest(cid, 1, cstate)
                })

                if (croom != "") {
                    $(this).prependTo($("#rcard-" + croom + " > .card-body"))
                }
            }
        }

        if (cicon != "none") {
            $(this).find(".iconi").attr("class", "iconi " + cicon)
        }

        $(this).attr("cinit", "1")
    })

    $(".gcard").each(function() {
        var group, cid, cinit
        group = $(this).find("h5.card-header").text()
        cinit = $(this).attr("cinit")
        cid = $(this).attr("id")

        if (cinit != "1") {
            $(this).find(".goffbuttons").on('click', function() {
                sendGroupPowerRequest(group, 0, cid)
            })
            $(this).find(".gonbuttons").on('click', function() {
                sendGroupPowerRequest(group, 1, cid)
            })
        }

        $(this).attr("cinit", "1")
    })

    $(".rcard").each(function() {
        var cinit, cgroup, hasoffdevices, hasondevices
        cinit = $(this).attr("cinit")
        cgroup = $(this).find("h4.card-header").text()
        hasoffdevices = hasondevices = false

        $(this).find(".card").each(function() {
            if (parseInt($(this).attr("cstate")) == 0) {
                hasoffdevices = true
            } else {
                hasondevices = true
            }
        })

        $(this).removeClass("border-danger")
        $(this).removeClass("border-warning")
        $(this).removeClass("border-success")
        $(this).find(".title-header").removeClass("bg-danger")
        $(this).find(".title-header").removeClass("bg-warning")
        $(this).find(".title-header").removeClass("bg-success")
        $(this).find(".d-count").removeClass("bg-danger")
        $(this).find(".d-count").removeClass("bg-warning")
        $(this).find(".d-count").removeClass("bg-success")
        if (hasoffdevices == false) {
            $(this).addClass("border-success")
            $(this).find(".title-header").addClass("bg-success")
            $(this).find(".d-count").addClass("bg-success")
        } else if (hasondevices == false) {
            $(this).addClass("border-danger")
            $(this).find(".title-header").addClass("bg-danger")
            $(this).find(".d-count").addClass("bg-danger")
        } else {
            $(this).addClass("border-warning")
            $(this).find(".title-header").addClass("bg-warning")
            $(this).find(".d-count").addClass("bg-warning")
        }

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
                $(this).find(".d-count").prepend(devlen + " device")
            } else {
                $(this).find(".d-count").prepend(devlen + " devices")
            }

            $(this).find(".goffbuttons").on('click', function() {
                sendGroupPowerRequest(cgroup, 0, "rcard-" + cgroup.toLowerCase())
            })
            $(this).find(".gonbuttons").on('click', function() {
                sendGroupPowerRequest(cgroup, 1, "rcard-" + cgroup.toLowerCase())
            })
        }

        $(this).attr("cinit", "1")
    })
}

function sendPowerRequest(devid, value, last_state, is_intensity=0) {
    abortPendingRequests()
    $(".card[cid=" + devid + "]").addClass("disabledbutton")
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "2",
                devid: devid,
                value: value,
                isintensity: is_intensity,
                skiptime: $('input[name=skiptime2]').is(":checked")
            },
        success: function(data){
            getOneResult(devid, last_state)
        }
    })
}

function sendGroupPowerRequest(group, value, devid) {
    abortPendingRequests()
    $("#"+devid).addClass("disabledbutton")
    runningRequests++
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "4",
                group: group,
                value: value,
                skiptime: $('input[name=skiptime2]').is(":checked")
            },
        success: function(data){
            $("#"+devid).removeClass("disabledbutton")
            getResultPost()
        }
    })
}

function sendModeRequest(devid, value, auto) {
    abortPendingRequests()
    $(".card[cid=" + devid + "]").addClass("disabledbutton")
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "3",
                mode: auto,
                devid: devid
            },
        success: function(data){
            getOneResult(devid, value)
        }
    })
}

function sendAllModeAuto() {
    abortPendingRequests()
    $(".dcard").addClass("disabledbutton")
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "6"
            },
        success: function(data){
            getResult()
        }
    })
}

function setLockDevice(lock, devid, last_state) {
    $("#"+devid).addClass("disabledbutton")
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "9",
                lock: lock,
                devid: devid
            },
        success: function(data){
            getOneResult(devid, last_state)
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
                reqtype: "7",
                module: amodule
            },
        success: function(data){
            $("#" + amodule + "-content").html(data)
        },
        error: function(data){
            console.log(data)
        }
    })
}