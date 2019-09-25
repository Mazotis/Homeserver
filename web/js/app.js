lastupdate = 0

$(document).ready(function() {
    getResult();
    lastupdate = new Date()
    window.onscroll = function (e) {
        if ((new Date() - lastupdate) > 20000 ) {
            lastupdate = new Date()
            getResultRefresh()
        }
    } 
})

function getResult() {
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

            var ghtml = '<div class="row"><div class="col-sm-3">'
            for (group in thedata.groups) {
                $("#groups").html("")
                if (cnt % Math.round(thedata.groups.length/4) === 0 && cnt != 0) {
                    ghtml += '</div><div class="col-sm-3">'
                }
                $("#groupcardmodel").find(".card-header").text(thedata.groups[group].charAt(0).toUpperCase() + thedata.groups[group].substr(1).toLowerCase())
                ghtml += '<div class="gcard" id="gcard' + cnt + '">' + $("#groupcardmodel").html() + '</div>'
                cnt = cnt + 1
            }
            ghtml += '</div></div>'
            $("#groups").html(ghtml)

            cnt = 0
            var html = '<div class="row"><div id="update-spin" class="col-12"><center><h5><div class="spinner-border noselect-nooverflow" role="status"></div>&nbsp;Updating device status...</h5></center></div><div class="col-sm-4">'
            for (_ in thedata.state) {
                if (cnt % Math.round(thedata.state.length/3) === 0 && cnt != 0) {
                    html += '</div><div class="col-sm-4">'
                }
                html += '<div class="dcard" id="card' + cnt + '">' + generateCard(cnt, thedata) + '</div>'
                cnt = cnt + 1
            }

            html += '</div></div></div>'
            $("#resultid").html(html)
            computeCards()
            getResultPost()
        }
    })
}

function getResultRefresh() {
    $("#update-spin").show()
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
            has_errors = false
            for (cnt in thedata.state) {
                if ($("#card" + cnt).find("div.mb-3").attr("cstate") != thedata.state[cnt]) {
                    $("#card" + cnt).find("div.mb-3").attr("cstate", thedata.state[cnt])
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
    $("#update-spin").show()
    $.ajax({
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
                if ($("#card" + cnt).find("div.mb-3").attr("cstate") != thedata.state[cnt]) {
                    $("#card" + cnt).find("div.mb-3").attr("cstate", thedata.state[cnt])
                    has_errors = true
                }
            }
            if (has_errors) {
                computeCards()
            }
            $("#update-spin").hide()
        }
    })        
}

function getOneResult(devid, last_state) {
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
            $("#card" + devid).html(generateCard(devid, thedata, last_state))
            computeCards()
            $("#card" + devid).removeClass("disabledbutton")
            getResultPost()
        }
    })
}

function generateCard(devid, data, last_state = null) {
    var mode
    data.mode[devid] ? mode = 1 : mode = 0
    $("#cardmodel").find("div.mb-3").attr("cstate", data.state[devid])
    $("#cardmodel").find("div.mb-3").attr("cid", devid)
    $("#cardmodel").find("div.mb-3").attr("cmode", mode)
    $("#cardmodel").find("div.mb-3").attr("cskiptime", data.op_skiptime[devid])
    $("#cardmodel").find("div.mb-3").attr("cforceoff", data.op_forceoff[devid])
    $("#cardmodel").find("div.mb-3").attr("cignoremode", data.op_ignoremode[devid])
    $("#cardmodel").find("div.mb-3").attr("cactiondelay", data.op_actiondelay[devid])
    $("#cardmodel").find("div.mb-3").attr("cicon", data.icon[devid])
    $("#cardmodel").find("div.mb-3").attr("ccolortype", data.colortype[devid])
    $("#cardmodel").find(".card-title").text(data.name[devid])
    $("#cardmodel").find(".text-muted").text(data.type[devid])
    $("#cardmodel").find("p.c-desc").text(data.description[devid])

    $("#cardmodel").find("p.errortext").hide()
    //TODO - Find a way to determine if a change between two colors has succeded (as the reported state from the lightserver differs from the "real" selection)
    if (last_state != data.state[devid] && !(last_state == 1 && data.state[devid] == "FFFFFF") 
        && last_state != null && !(last_state.length == 6 && data.state[devid].length == 6 
            && data.state[devid] != "000000" && data.state[devid] != "FFFFFF") &&
            data.state[devid] != "-2") {
        $("#cardmodel").find("p.errortext").show()
    }

    html = $("#cardmodel").html()

    return html
}

function computeCards() {
    $(".dcard .card").each(function() {
        var cstate, cid, cmode, ccolortype, cinit
        cinit = $(this).attr("cinit")
        cstate = $(this).attr("cstate")
        cid = $(this).attr("cid")
        cmode = $(this).attr("cmode")
        cforceoff = $(this).attr("cforceoff")
        cignoremode = $(this).attr("cignoremode")
        cskiptime = $(this).attr("cskiptime")
        cactiondelay = $(this).attr("cactiondelay")
        cicon = $(this).attr("cicon")
        ccolortype = $(this).attr("ccolortype")

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
                $(this).find(".colorpick").show()
                if (cinit != "1") {
                    $(this).find(".colorpick").on("change", function(ev) {
                        color = ev.currentTarget.firstElementChild.value.substr(1)
                        sendPowerRequest(cid, color)
                    })
                }
            }

            if (["100"].includes(ccolortype)) {
                $(this).find(".sliderpick").attr("value", cstate)
                $(this).find(".slider-text").html(cstate)
                $(this).find(".sliderpick").show()
                if (cinit != "1") {
                    $(this).find(".sliderpick").on("change", function() {
                        color = $(this).find("input").val()
                        sendPowerRequest(cid, color)
                    })
                    $(this).find(".sliderpick").on("input", function() {
                        color = $(this).find("input").val()
                        $(this).find(".slider-text").html(color)
                    })
                }
            }

            if (cinit != "1") {
                $(this).find(".radiomode :input").on('change', function() {
                    sendModeRequest(cid, cstate, $(this).val())
                })
                $(this).find(".offbuttons").on('click', function() {
                    sendPowerRequest(cid, 0)
                })
                $(this).find(".onbuttons").on('click', function() {
                    sendPowerRequest(cid, 1)
                })
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
}

function sendPowerRequest(devid, value) {
    $("#card" + devid).addClass("disabledbutton")
    $.ajax({
        type: "POST",
        url: ".",
        dataType: "text",
        data: {
                request: "True",
                reqtype: "2",
                devid: devid,
                value: value,
                skiptime: $('input[name=skiptime2]').is(":checked")
            },
        success: function(data){
            getOneResult(devid, value)
        }
    })
}

function sendGroupPowerRequest(group, value, devid) {
    $("#"+devid).addClass("disabledbutton")
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
        }
    })
}

function sendModeRequest(devid, value, auto) {
    $("#card" + devid).addClass("disabledbutton")
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