#!/bin/bash
date --date="`echo $(curl -s https://weather.com/weather/today/l/$1 | sed 's/<span/\n/g' | sed 's/<\/span>/\n/g'  | grep -E "dp0-details-sunrise|dp0-details-sunset" | tr -d '\n' | sed 's/>/ /g' | cut -d " " -f 4,8) | awk '{ print $2}'` PM" +%R &
exit