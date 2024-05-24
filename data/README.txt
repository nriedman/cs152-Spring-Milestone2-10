**************Information on how to use our Multi-ideology ISIS/Jihadist White Supremacist Dataset(MIWS)for Multi-class Extremism Text Classification ************

Folder name: Seed_MIWS 
Sub Folder 1 : Seed_Dataset
Inside this folder there are two .csv files.
1) ISIS/Jihadist_Seed_Dataset
2) White_Supremacist_Seed_Dataset

These files have common features as:
***************************** Common Features in Seed ******************************************************
*********Source :- Contains Author, Article Name or Hyperlink to Article************************************
*********Type_of_Source :- Whether Source is Research Article or Report or Website**************************
*********Text :- Contains Extremist Text provided in Source*************************************************
*********Ideology :- Ideology of Text mentioned in Source i.e. ISIS/Jihadist or White Supremacist***********
*********Label :- Labels for Text provided by Source i.e. Propaganda, Radicalization or Recruitment*********
*********Geographical_Location :- Location mentioned in Text. Geographical Location is manually identified**
*********Author_Country_Affiliation :- Country of origin of Research Article, Report or Website in Source***

Sub Folder 2 : MIWS
Inside this folder ther is one .csv file:

It contains features as:
*****************************Features in MIWS********************************************************************************
**********Tweet_ID :- Unique Identification for a Tweet provided by Twitter**************************************************
**********Created_Date :- Date and Time at whic Tweet was created or posted**************************************************
**********Geo_Enabled :- Boolean value. True if location is made public by User**********************************************
**********Geographical_Location :- Manually extracted list of Locations within the tweet. 'Undefined' if no location present*
**********Ideology :- Manually provided during Tweet Collection i.e. ISIS/Jihadist or White Supremacist**********************
**********Labels :-  Annotated by comparing with Seed, i.e. Propaganda, Radicalization and Recruitment*********************** 

MIWS file can be used to collect tweets and train model for extremism detection.