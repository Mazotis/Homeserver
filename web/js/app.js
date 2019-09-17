lastupdate = 0

$(document).ready(function() {
    getResult();
    lastupdate = new Date()
    window.onscroll = function (e) {
        if ((new Date() - lastupdate) > 30000 ) {
            lastupdate = new Date()
            getResultPost()
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
            console.log(thedata)

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
    $("#cardmodel").find("div.mb-3").attr("cicon", data.icon[devid])
    $("#cardmodel").find(".card-title").text(data.name[devid])
    $("#cardmodel").find(".text-muted").text(data.type[devid])
    $("#cardmodel").find("p.c-desc").text(data.description[devid])

    if (last_state != parseInt(data.state[devid]) &&  !(last_state != 0 && parseInt(data.state[devid]) != 0) && last_state != null) {
        $("#cardmodel").find("p.errortext").show()
    } else {
        $("#cardmodel").find("p.errortext").hide()
    }

    html = $("#cardmodel").html()

    return html
}

function computeCards() {
    $(".dcard .card").each(function() {
        var cstate, cid, cmode
        cstate = $(this).attr("cstate")
        cid = $(this).attr("cid")
        cmode = $(this).attr("cmode")
        cforceoff = $(this).attr("cforceoff")
        cignoremode = $(this).attr("cignoremode")
        cskiptime = $(this).attr("cskiptime")
        cicon = $(this).attr("cicon")

        if (cstate == "0" || (!isNaN(cstate) && parseInt(cstate) == 0)) {
            $(this).find(".offbuttons").attr('disabled', true)
            $(this).find(".onbuttons").attr('disabled', false)
            $(this).find(".card-header").addClass("bg-danger")
            $(this).find(".card-header").removeClass("bg-success")
            $(this).addClass("border-danger")
            $(this).removeClass("border-success")
        } else {
            $(this).find(".offbuttons").attr('disabled', false)
            $(this).find(".onbuttons").attr('disabled', true)
            $(this).find(".card-header").addClass("bg-success")
            $(this).find(".card-header").removeClass("bg-danger")
            $(this).addClass("border-success")
            $(this).removeClass("border-danger")
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

        if (cicon != "none") {
            $(this).find(".iconi").attr("class", "iconi " + cicon)
        }

        $(this).find(".radiomode :input").on('change', function() {
            sendModeRequest(cid, cstate, $(this).val())
        })
        $(this).find(".offbuttons").on('click', function() {
            sendPowerRequest(cid, 0)
        })
        $(this).find(".onbuttons").on('click', function() {
            sendPowerRequest(cid, 1)
        })
    })

    $(".gcard").each(function() {
        var group, cid
        group = $(this).find("h5.card-header").text()
        cid = $(this).attr("id")
        $(this).find(".goffbuttons").on('click', function() {
            sendGroupPowerRequest(group, 0, cid)
        })
        $(this).find(".gonbuttons").on('click', function() {
            sendGroupPowerRequest(group, 1, cid)
        })
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