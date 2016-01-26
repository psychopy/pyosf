A pure Python library for simple sync with Open Science Framework

This package is for simple synchronisation of files from the local file space to the Open Science Framework (OSF). There is a more complex fully-featured sync package by the Center for Open Science,
who created OSF, called [osf-sync](https://github.com/CenterForOpenScience/osf-sync)
	
The OSF official package is designed for continuous automated synchronisation of many projects (a la Dropbox). We needed something simpler (for combination with PsychoPy). This package aims to perform basic search/login/sync operations with single projects on OSF but only when instructed to do so (no continuous sync).

In implementation it differs from osf-sync in the following ways:
	* fewer dependencies
	* support for Python2.x
	* no GUI included (yet)
	* local database of files saved as flat json format (no database)
	* simpler handling of sync resolution rules(?)

It can be distributed freely under the MIT license.
