# Overview

You must build a connector in Python that periodically fetches files from the Autodesk Construction Cloud API and Google Drive API, gets the file link, title, date created, date updated, project id and user id, and pushes it to a supabase table. This action will be run every 5 minutes for each enumerated endpoint, and it must only fetch files that have not been pushed to the supabase table yet, based on the created and updated timestamp. 

The endpoints should be initially given in a data array, which has objects (hashmaps) for the endpoint type + endpoint details + project id + user id. 

It should be the foundation of a feature implemented in a SaaS. Therefore, room must be made for adding new endpoints and schedules.  


## Task 1