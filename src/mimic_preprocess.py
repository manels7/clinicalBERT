import pandas as pd
import numpy as np
import pickle
import os
import csv
import sys
import matplotlib.pyplot as plt
import json



# def featureToIdx(features):
#     feature2idx = {}
#     feature2idx[0] = 0
#     idx=0
#     for i, entry in enumerate(features):
#         if isinstance(entry, str):
#             entry = int(entry.strip())
#         print(i, entry)
#         feature2idx[entry] = i
#     return feature2idx

# def featureToIdx_original(features):
#     feature2idx = {}
#     feature2idx[int(0)] = 0 #will be used to mask padding "codes" in the model
#     idx=1
#     for entry in features:
#         print(idx, entry)
#         feature2idx[int(entry)] = idx
#         idx+=1
#     return feature2idx

def featureToIdx(features):
    feature2idx = {}
    feature2idx["0"] = 0 #will be used to mask padding "codes" in the model
    idx=1
    for entry in features:
        if entry in feature2idx.keys():
            pass
        else:# print(idx, entry)
            feature2idx[entry] = idx
            idx+=1
    return feature2idx


def getICDlevel1(icd9_code):
    """
    This method extracts the first level of hierarchy of an ICD code:
        - Procedure codes start with P_xxxx and only have 2 digits in the first level so we extract P_xx
        - Diagnoses codes start with D_ and can have the following formats (1) Exxx (2) Vxx (3) xxx 
    """
    if icd9_code.startswith("P"):
        return icd9_code[:4]
    elif icd9_code.startswith("D"):
        if icd9_code.startswith("D_E"):
            return icd9_code[:6]
        else:
            return icd9_code[:5]


def writeToJSON(content, filepath):
    if os.path.isfile(filepath):
        with open(filepath, 'r') as file:
            baseContent = json.load(file)
        content.update(baseContent)
        print("Added content to previously existing file at {}!!".format(filepath))
    with open(filepath, 'w') as file:
        json.dump(content, file)


def countCodesPerType(Icd9CcsMap):
    diagDict = dict()
    procDict = dict()
    for icd9, ccs in Icd9CcsMap.items():
        if icd9[0] == "D":
            diagDict[icd9] = ccs
        elif icd9[0] == "P":
            procDict[icd9] = ccs
    print("Number of Diagnosis ICD9 codes in map: {}.".format(len(diagDict.keys())))
    print("Number of Diagnosis CCS codes in map: {}.".format(len(set(diagDict.values()))))
    print("Number of Procedure ICD9 codes in map: {}.".format(len(procDict.keys())))
    print("Number of Procedure CCS codes in map: {}.".format(len(set(procDict.values()))))

# def map_ICD9_to_CCS(pandasDataFrame):
#     with open('../data/extended/ICDandCCSmappings/merged_icdccs_codes.json','r') as file:
#         icd9TOCCS_Map = json.load(file)
#     mappedCCSList = []
#     unmapped=0
#     mapped=0
#     dfDict = pandasDataFrame.to_dict('records')
#     for row in dfDict:
#         hadm_id = row["HADM_ID"]
#         ICD9s_List = row["ICD9_CODE"]
#         tempCodeList = []
#         for ICD9 in ICD9s_List:
#             try:
#                 CCS_code = icd9TOCCS_Map[ICD9]
#                 tempCodeList.append(CCS_code)
#                 mapped+=1
#             except KeyError:
#                 tempCodeList.append("-1") #Used for NaN entries
#                 unmapped+=1

#         mappedCCSList.append(tempCodeList)

#     # This "-1" is necessary because in proc_icd9 there exist empty entries (where no proc_icd9 codes were assigned to the patient)
#     # These empty entries will be processed as "-1" entries later on, before being fed to the model as input
#     icd9Set=set(icd9TOCCS_Map.keys())
#     icd9Set.add("-1")
#     if not os.path.isfile("../data/extended/Icd9ToIdx.json"):
#         icd9Set = sorted({entry.strip() for entry in icd9Set})
#         icd9ToIdx = featureToIdx(icd9Set)
#         writeToJSON(icd9ToIdx, "../data/extended/Icd9ToIdx.json")

#     ccsSet = set(icd9TOCCS_Map.values())
#     ccsSet.add("-1")
#     if not os.path.isfile("../data/extended/CCSToIdx.json"):
#         ccsSet = sorted({entry.strip() for entry in ccsSet})
#         ccsToIdx = featureToIdx(ccsSet)
#         writeToJSON(ccsToIdx, "../data/extended/CCSToIdx.json")

#     print('-Total number (complete set) of ICD9 codes (diag + proc): {}'.format(len(icd9Set)))
#     print('-Total number (complete set) of CCS codes (diag + proc): {}'.format(len(ccsSet)))
#     print("-Total of mapped/unmapped entries {}/{}".format(mapped,unmapped))
#     return mappedCCSList

def map_ICD9_to_CCS(pandasDataFrame):
    with open('../data/extended/ICDandCCSmappings/merged_icdccs_codes.json','r') as file:
        icd9TOCCS_Map = json.load(file)
    mappedSmallICDList = []
    mappedCCSList = []
    unmapped=0
    mapped=0  
    for row in pandasDataFrame.itertuples():
        tempSmallICDCodeList = []
        tempCCSCodeList = []
        for ICD9 in row.ICD9_CODE:
            smallICD = getICDlevel1(ICD9)
            if smallICD not in tempSmallICDCodeList: tempSmallICDCodeList.append(smallICD)
            try:
                CCS_code = icd9TOCCS_Map[ICD9]
                tempCCSCodeList.append(CCS_code)
                mapped+=1
            except KeyError:
    ## This was previously added but we decided to simply not introduce more noise if the map is unsuccessful
                # tempCCSCodeList.append("0") #Used for NaN entries
                unmapped+=1
        mappedSmallICDList.append(tempSmallICDCodeList)
        mappedCCSList.append(tempCCSCodeList)
    with open('../data/extended/ICDandCCSmappings/merged_icd_text.json','r') as file:
        icd9map = json.load(file)

    if not os.path.isfile("../data/extended/smallIcd9ToIdx.json"):
        smallICDset = set()
        for code in icd9map.keys():
            smallICDset.add(getICDlevel1(code))
        smallIcd9ToIdx = featureToIdx(smallICDset)
        writeToJSON(smallIcd9ToIdx, "../data/extended/smallIcd9ToIdx.json")

    # A "0" is added during featureToIdx because in proc_icd9 there exist empty entries (where no proc_icd9 codes were assigned to the patient)
    # These empty entries will be processed as "0" entries later on, before being fed to the model as input
    if not os.path.isfile("../data/extended/Icd9ToIdx.json"):
        icd9ToIdx = featureToIdx(set(icd9map.keys()))
        writeToJSON(icd9ToIdx, "../data/extended/Icd9ToIdx.json")

    ccsSet = set(icd9TOCCS_Map.values())
    if not os.path.isfile("../data/extended/CCSToIdx.json"):
        ccsSet = {entry.strip() for entry in ccsSet}
        ccsToIdx = featureToIdx(ccsSet)
        writeToJSON(ccsToIdx, "../data/extended/CCSToIdx.json")
    print('-Total number (complete set) of ICD9 codes (diag + proc): {}'.format(len(set(icd9map.keys()))))
    print('-Total number (complete set) of CCS codes (diag + proc): {}'.format(len(ccsSet)))
    print("-Total of mapped/unmapped entries {}/{}".format(mapped,unmapped))
    return mappedCCSList, mappedSmallICDList


def get_unique_ordered_medication(pandasDataFrame):
    with open("../data/extended/NDCmappings/ndc_cui_map.json", "r") as file:
        ndcCuiMap = json.load(file)
    RxNormNdcs = set(ndcCuiMap.keys())
    mapped=0
    unmapped=0
    if "NDC" in pandasDataFrame.columns.values:
        column = "NDC"
    elif "DRUG" in pandasDataFrame.columns.values:
        column = "DRUG"
    # counter = 0
    unique_cuis_list = []
    for index in pandasDataFrame.index:
        used_medications = set()
        #unique_medication = [x for x in pandasDataFrame.loc[index, column] if x not in used_medications and (used_medications.add(x) or True)]
        unique_medication = []
        temp_cuis_list = []
        for value in pandasDataFrame.loc[index, column]:
            if value not in used_medications and (used_medications.add(value) or True):
                if pd.isna(value) or value==0.0 or str(int(value)) not in RxNormNdcs: #Attention, the last clause leads to codes not appearing in the set
                    # if (not pd.isna(value) and not value==0.0):
                    #     print(value)
                    #     counter+=1
                    value = 0 # Swapping NaNs to a default numerical number that is not used elsewhere
                if value is not 0: unique_medication.append(str(int(value)))
            if (int(value) is not 0) and (str(int(value)) in RxNormNdcs):
                mapped+=1
            else:
                unmapped+=1
            try:
                cui = ndcCuiMap[str(int(value))]
                if cui not in temp_cuis_list: temp_cuis_list.append(cui)
            except KeyError:
                pass
        unique_cuis_list.append(temp_cuis_list)
        pandasDataFrame.at[index, column] = unique_medication
    ndcsToIdx = featureToIdx(RxNormNdcs)
    cuisToIdx = featureToIdx(set(ndcCuiMap.values()))
    if not os.path.isfile("../data/extended/NDCToIdx.json"): writeToJSON(ndcsToIdx, "../data/extended/NDCToIdx.json")
    if not os.path.isfile("../data/extended/cui_NDCToIdx.json"): writeToJSON(cuisToIdx, "../data/extended/cui_NDCToIdx.json")
    # print("mapped: {}, unmapped: {}".format(mapped, unmapped))
    # print(counter)
    return pandasDataFrame, unique_cuis_list



df_adm = pd.read_csv('/backup/mimiciii/ADMISSIONS.csv.gz', compression="gzip")
df_adm.ADMITTIME = pd.to_datetime(df_adm.ADMITTIME, format = '%Y-%m-%d %H:%M:%S', errors = 'coerce')
df_adm.DISCHTIME = pd.to_datetime(df_adm.DISCHTIME, format = '%Y-%m-%d %H:%M:%S', errors = 'coerce')
df_adm.DEATHTIME = pd.to_datetime(df_adm.DEATHTIME, format = '%Y-%m-%d %H:%M:%S', errors = 'coerce')

df_adm = df_adm.sort_values(['SUBJECT_ID','ADMITTIME'])
df_adm = df_adm.reset_index(drop = True)
df_adm['NEXT_ADMITTIME'] = df_adm.groupby('SUBJECT_ID').ADMITTIME.shift(-1)
df_adm['NEXT_ADMISSION_TYPE'] = df_adm.groupby('SUBJECT_ID').ADMISSION_TYPE.shift(-1)

df_adm['PREV_DISCHTIME'] = df_adm.groupby('SUBJECT_ID').DISCHTIME.shift(1)
df_adm['PREV_ADMISSION_TYPE'] = df_adm.groupby('SUBJECT_ID').ADMISSION_TYPE.shift(1)

rows = df_adm.NEXT_ADMISSION_TYPE == 'ELECTIVE'
df_adm.loc[rows,'NEXT_ADMITTIME'] = pd.NaT
df_adm.loc[rows,'NEXT_ADMISSION_TYPE'] = np.NaN

# rows = df_adm.PREV_ADMISSION_TYPE == 'ELECTIVE'
# df_adm.loc[rows,'PREV_DISCHTIME'] = pd.NaT
# df_adm.loc[rows,'PREV_ADMISSION_TYPE'] = np.NaN

df_adm = df_adm.sort_values(['SUBJECT_ID','ADMITTIME'])

#When we filter out the "ELECTIVE", we need to correct the next admit time for these admissions since there might be 'emergency' next admit after "ELECTIVE"
df_adm[['NEXT_ADMITTIME','NEXT_ADMISSION_TYPE']] = df_adm.groupby(['SUBJECT_ID'])[['NEXT_ADMITTIME','NEXT_ADMISSION_TYPE']].fillna(method = 'bfill')
df_adm['DAYS_NEXT_ADMIT'] = (df_adm.NEXT_ADMITTIME - df_adm.DISCHTIME).dt.total_seconds()/(24*60*60)
df_adm[['PREV_DISCHTIME','PREV_ADMISSION_TYPE']] = df_adm.groupby(['SUBJECT_ID'])[['PREV_DISCHTIME','PREV_ADMISSION_TYPE']].fillna(method = 'bfill')
df_adm['DAYS_PREV_ADMIT'] = (df_adm.ADMITTIME - df_adm.PREV_DISCHTIME).dt.total_seconds()/(24*60*60)

df_adm['OUTPUT_LABEL'] = (df_adm.DAYS_NEXT_ADMIT < 30).astype('int')
### filter out newborn and death
df_adm = df_adm[df_adm['ADMISSION_TYPE']!='NEWBORN']
df_adm = df_adm[df_adm.DEATHTIME.isnull()]
df_adm['DURATION']  = (df_adm['DISCHTIME']-df_adm['ADMITTIME']).dt.total_seconds()/(24*60*60)


df_diagnoses = pd.read_csv('/backup/mimiciii/DIAGNOSES_ICD.csv.gz', compression="gzip")
df_diagnoses = df_diagnoses[df_diagnoses.ICD9_CODE.notna()]
df_diagnoses = df_diagnoses.sort_values(['HADM_ID','SEQ_NUM'], ascending=True)
df_diagnoses = df_diagnoses.reset_index(drop = True)
df_diagnoses.ICD9_CODE = "D_" + df_diagnoses.ICD9_CODE.astype(str)
df_diag_listing = df_diagnoses.groupby('HADM_ID')['ICD9_CODE'].apply(list)
df_diag_listing = df_diag_listing.reset_index()
diagnosesCCS, smallICDs = map_ICD9_to_CCS(df_diag_listing)
df_diag_listing['SMALL_DIAG_ICD9'] = smallICDs
df_diag_listing['DIAG_CCS'] = diagnosesCCS

df_adm = pd.merge(df_adm,
                  df_diag_listing[['HADM_ID','ICD9_CODE','SMALL_DIAG_ICD9','DIAG_CCS']],
                  on = ['HADM_ID'],
                  how = 'left')

df_adm = df_adm.rename(columns={'ICD9_CODE': 'DIAG_ICD9'})

df_procedures = pd.read_csv('/backup/mimiciii/PROCEDURES_ICD.csv.gz', compression="gzip")
df_procedures = df_procedures.sort_values(['HADM_ID','SEQ_NUM'], ascending=True)
df_procedures = df_procedures.reset_index(drop = True)
df_procedures.ICD9_CODE = "P_" + df_procedures.ICD9_CODE.astype(str)
df_proc_listing = df_procedures.groupby('HADM_ID')['ICD9_CODE'].apply(list)
df_proc_listing = df_proc_listing.reset_index()
proceduresCCS, smallICDs = map_ICD9_to_CCS(df_proc_listing)
df_proc_listing['SMALL_PROC_ICD9'] = smallICDs
df_proc_listing['PROC_CCS'] = proceduresCCS

df_adm = pd.merge(df_adm,
                  df_proc_listing[['HADM_ID','ICD9_CODE','SMALL_PROC_ICD9','PROC_CCS']],
                  on = ['HADM_ID'],
                  how = 'left')

df_adm = df_adm.rename(columns={'ICD9_CODE': 'PROC_ICD9'})


df_medication = pd.read_csv('/backup/mimiciii/PRESCRIPTIONS.csv.gz', compression="gzip")
df_medication = df_medication.sort_values(['HADM_ID','STARTDATE'], ascending=True)
df_medication = df_medication.reset_index(drop = True)
# df_med_listing1 = df_medication.groupby('HADM_ID')['DRUG'].apply(list)
# df_med_listing1 = df_med_listing1.reset_index()
df_med_listing = df_medication.groupby('HADM_ID')['NDC'].apply(list)
df_med_listing = df_med_listing.reset_index()
df_med_listing, cuis = get_unique_ordered_medication(df_med_listing) #now the list of medication only contains unique medications, not a long list of many repeated meds
df_med_listing['CUI'] = cuis

df_adm = pd.merge(df_adm,
                  df_med_listing[['HADM_ID','NDC','CUI']],
                  on = ['HADM_ID'],
                  how = 'left')

df_adm['NEXT_SMALL_DIAG_ICD9'] = df_adm.groupby('SUBJECT_ID').SMALL_DIAG_ICD9.shift(-1)
df_adm['NEXT_DIAG_CCS'] = df_adm.groupby('SUBJECT_ID').DIAG_CCS.shift(-1)
df_adm['NEXT_SMALL_PROC_ICD9'] = df_adm.groupby('SUBJECT_ID').SMALL_PROC_ICD9.shift(-1)
df_adm['NEXT_PROC_CCS'] = df_adm.groupby('SUBJECT_ID').PROC_CCS.shift(-1)
df_adm['NEXT_CUI'] = df_adm.groupby('SUBJECT_ID').CUI.shift(-1)

df_notes = pd.read_csv('/backup/mimiciii/NOTEEVENTS.csv.gz', compression="gzip")
df_notes = df_notes.sort_values(by=['SUBJECT_ID','HADM_ID','CHARTDATE'])
df_adm_notes = pd.merge(df_adm[['SUBJECT_ID','HADM_ID','ADMITTIME','DISCHTIME','DAYS_NEXT_ADMIT','DAYS_PREV_ADMIT','NEXT_ADMITTIME','ADMISSION_TYPE',
                                'DEATHTIME','OUTPUT_LABEL','DURATION','DIAG_ICD9','SMALL_DIAG_ICD9','DIAG_CCS','PROC_ICD9','SMALL_PROC_ICD9',
                                'PROC_CCS','NDC', 'CUI','NEXT_SMALL_DIAG_ICD9', 'NEXT_DIAG_CCS', 'NEXT_SMALL_PROC_ICD9', 'NEXT_PROC_CCS', 'NEXT_CUI']],
                        df_notes[['SUBJECT_ID','HADM_ID','CHARTDATE','CHARTTIME','TEXT','CATEGORY']],
                        on = ['SUBJECT_ID','HADM_ID'],
                        how = 'left')

df_adm_notes["ADMITTIME_C"] = df_adm_notes.ADMITTIME.apply(lambda x: str(x).split(' ')[0])
df_adm_notes['ADMITTIME_C'] = pd.to_datetime(df_adm_notes.ADMITTIME_C, format = '%Y-%m-%d', errors = 'coerce')
df_adm_notes['CHARTDATE'] = pd.to_datetime(df_adm_notes.CHARTDATE, format = '%Y-%m-%d', errors = 'coerce')
df_adm_notes['CHARTTIME'] = pd.to_datetime(df_adm_notes.CHARTTIME, format = '%Y-%m-%d %H:%M:%S', errors = 'coerce')
df_adm_notes = df_adm_notes.sort_values(by=['SUBJECT_ID','HADM_ID','CHARTDATE','CHARTTIME'])
df_adm_notes = df_adm_notes.reset_index(drop = True)


### If Discharge Summary
df_discharge = df_adm_notes[df_adm_notes['CATEGORY'] == 'Discharge summary']
# multiple discharge summary for one admission -> after examination -> replicated summary -> replace with the last one
df_discharge = (df_discharge.groupby(['SUBJECT_ID','HADM_ID']).nth(-1)).reset_index()
df_discharge=df_discharge[df_discharge['TEXT'].notnull()]


### If Less than n days on admission notes (Early notes)
def less_n_days_data (df_adm_notes, n):
    df_less_n = df_adm_notes[((df_adm_notes['CHARTDATE']-df_adm_notes['ADMITTIME_C']).dt.total_seconds()/(24*60*60))<n]
    df_less_n = df_less_n[df_less_n['TEXT'].notnull()]
    #concatenate first
    df_concat = pd.DataFrame(df_less_n.groupby('HADM_ID')['TEXT'].apply(lambda x: "%s" % ' '.join(x))).reset_index()
    df_concat['OUTPUT_LABEL'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].OUTPUT_LABEL.values[0])
    df_concat['SUBJECT_ID'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].SUBJECT_ID.values[0])
    df_concat['ADMITTIME'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].ADMITTIME.values[0])
    df_concat['DAYS_NEXT_ADMIT'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].DAYS_NEXT_ADMIT.values[0])
    df_concat['DAYS_PREV_ADMIT'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].DAYS_PREV_ADMIT.values[0])
    df_concat['DURATION'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].DURATION.values[0])
    df_concat['DIAG_ICD9'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].DIAG_ICD9.values[0])
    df_concat['SMALL_DIAG_ICD9'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].SMALL_DIAG_ICD9.values[0])
    df_concat['DIAG_CCS'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].DIAG_CCS.values[0])
    df_concat['PROC_ICD9'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].PROC_ICD9.values[0])
    df_concat['SMALL_PROC_ICD9'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].SMALL_PROC_ICD9.values[0])
    df_concat['PROC_CCS'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].PROC_CCS.values[0])
    df_concat['NDC'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].NDC.values[0])
    df_concat['CUI'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].CUI.values[0])
    df_concat['NEXT_SMALL_DIAG_ICD9'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].NEXT_SMALL_DIAG_ICD9.values[0])
    df_concat['NEXT_DIAG_CCS'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].NEXT_DIAG_CCS.values[0])
    df_concat['NEXT_SMALL_PROC_ICD9'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].NEXT_SMALL_PROC_ICD9.values[0])
    df_concat['NEXT_PROC_CCS'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].NEXT_PROC_CCS.values[0])
    df_concat['NEXT_CUI'] = df_concat['HADM_ID'].apply(lambda x: df_less_n[df_less_n['HADM_ID']==x].NEXT_CUI.values[0])  
    df_concat = df_concat.sort_values(by=['SUBJECT_ID','HADM_ID'])
    df_concat = df_concat.reset_index(drop = True)
    return df_concat

df_less_2 = less_n_days_data(df_adm_notes, 2)
df_less_3 = less_n_days_data(df_adm_notes, 3)

print("LOADED THE DATA")

import re
def preprocess1(x):
    y=re.sub('\\[(.*?)\\]','',x) #remove de-identified brackets
    y=re.sub('[0-9]+\.','',y) #remove 1.2. since the segmenter segments based on this
    y=re.sub('dr\.','doctor',y)
    y=re.sub('m\.d\.','md',y)
    y=re.sub('admission date:','',y)
    y=re.sub('discharge date:','',y)
    y=re.sub('--|__|==','',y)
    return y

def preprocessing(df_less_n):
    df_less_n['TEXT']=df_less_n['TEXT'].fillna(' ')
    df_less_n['TEXT']=df_less_n['TEXT'].str.replace('\n',' ')
    df_less_n['TEXT']=df_less_n['TEXT'].str.replace('\r',' ')
    df_less_n['TEXT']=df_less_n['TEXT'].apply(str.strip)
    df_less_n['TEXT']=df_less_n['TEXT'].str.lower()
    df_less_n['TEXT']=df_less_n['TEXT'].apply(lambda x: preprocess1(x))
    #to get 318 words chunks for readmission tasks
    from tqdm import tqdm
    df_len = len(df_less_n)
    #want=pd.DataFrame({'ID':[],'DIAG_ICD9':[],'DIAG_CCS':[],'PROC_ICD9':[],'PROC_CCS':[],'NDC':[],'TEXT':[],'Label':[]})
    want=pd.DataFrame({'HADM_ID':[],'SUBJECT_ID':[],'ADMITTIME':[],'DAYS_NEXT_ADMIT':[],'DAYS_PREV_ADMIT':[],'DURATION':[],'DIAG_ICD9':[],
                       'SMALL_DIAG_ICD9':[],'DIAG_CCS':[],'PROC_ICD9':[],'SMALL_PROC_ICD9':[],'PROC_CCS':[],'NDC':[],'CUI':[],'TEXT':[],'Label':[],
                       'NEXT_SMALL_DIAG_ICD9':[],'NEXT_DIAG_CCS':[],'NEXT_SMALL_PROC_ICD9':[],'NEXT_PROC_CCS':[],'NEXT_CUI':[]})
    for i in tqdm(range(df_len)):
        x=df_less_n.TEXT.iloc[i].split()
        n=int(len(x)/318)
        for j in range(n):
            want=want.append({'TEXT':' '.join(x[j*318:(j+1)*318]),'Label':df_less_n.OUTPUT_LABEL.iloc[i],'HADM_ID':df_less_n.HADM_ID.iloc[i],
                              'SUBJECT_ID':df_less_n.SUBJECT_ID.iloc[i],'ADMITTIME':df_less_n.ADMITTIME.iloc[i],
                              'DAYS_NEXT_ADMIT':df_less_n.DAYS_NEXT_ADMIT.iloc[i], 'DAYS_PREV_ADMIT':df_less_n.DAYS_PREV_ADMIT.iloc[i], 
                              'DURATION':df_less_n.DURATION.iloc[i], 'NDC':df_less_n.NDC.iloc[i], 
                              'DIAG_ICD9':df_less_n.DIAG_ICD9.iloc[i],'DIAG_CCS':df_less_n.DIAG_CCS.iloc[i],
                              'PROC_ICD9':df_less_n.PROC_ICD9.iloc[i],'PROC_CCS':df_less_n.PROC_CCS.iloc[i],
                              'SMALL_DIAG_ICD9':df_less_n.SMALL_DIAG_ICD9.iloc[i],'SMALL_PROC_ICD9':df_less_n.SMALL_PROC_ICD9.iloc[i],
                              'CUI':df_less_n.CUI.iloc[i], 'NEXT_CUI':df_less_n.NEXT_CUI.iloc[i],
                              'NEXT_SMALL_DIAG_ICD9':df_less_n.NEXT_SMALL_DIAG_ICD9.iloc[i], 'NEXT_SMALL_PROC_ICD9':df_less_n.NEXT_SMALL_PROC_ICD9.iloc[i],
                              'NEXT_DIAG_CCS':df_less_n.NEXT_DIAG_CCS.iloc[i], 'NEXT_PROC_CCS':df_less_n.NEXT_PROC_CCS.iloc[i],}, ignore_index=True)                           
        if len(x)%318>10:
            want=want.append({'TEXT':' '.join(x[-(len(x)%318):]),'Label':df_less_n.OUTPUT_LABEL.iloc[i],'HADM_ID':df_less_n.HADM_ID.iloc[i],
                              'SUBJECT_ID':df_less_n.SUBJECT_ID.iloc[i],'ADMITTIME':df_less_n.ADMITTIME.iloc[i],
                              'DAYS_NEXT_ADMIT':df_less_n.DAYS_NEXT_ADMIT.iloc[i], 'DAYS_PREV_ADMIT':df_less_n.DAYS_PREV_ADMIT.iloc[i], 
                              'DURATION':df_less_n.DURATION.iloc[i], 'NDC':df_less_n.NDC.iloc[i],
                              'DIAG_ICD9':df_less_n.DIAG_ICD9.iloc[i],'DIAG_CCS':df_less_n.DIAG_CCS.iloc[i],
                              'PROC_ICD9':df_less_n.PROC_ICD9.iloc[i],'PROC_CCS':df_less_n.PROC_CCS.iloc[i],
                              'SMALL_DIAG_ICD9':df_less_n.SMALL_DIAG_ICD9.iloc[i],'SMALL_PROC_ICD9':df_less_n.SMALL_PROC_ICD9.iloc[i],
                              'CUI':df_less_n.CUI.iloc[i], 'NEXT_CUI':df_less_n.NEXT_CUI.iloc[i],
                              'NEXT_SMALL_DIAG_ICD9':df_less_n.NEXT_SMALL_DIAG_ICD9.iloc[i], 'NEXT_SMALL_PROC_ICD9':df_less_n.NEXT_SMALL_PROC_ICD9.iloc[i],
                              'NEXT_DIAG_CCS':df_less_n.NEXT_DIAG_CCS.iloc[i], 'NEXT_PROC_CCS':df_less_n.NEXT_PROC_CCS.iloc[i],}, ignore_index=True)                     
    return want

df_discharge = preprocessing(df_discharge)
df_less_2 = preprocessing(df_less_2)
df_less_3 = preprocessing(df_less_3)

print("DATA PREPROCESSED")



### An example to get the train/test/split with random state:
### note that we divide on patient admission level and share among experiments, instead of notes level.
### This way, since our methods run on the same set of admissions, we can see the
### progression of readmission scores.

readmit_ID = df_adm[df_adm.OUTPUT_LABEL == 1].HADM_ID
not_readmit_ID = df_adm[df_adm.OUTPUT_LABEL == 0].HADM_ID
#subsampling to get the balanced pos/neg numbers of patients for each dataset
not_readmit_ID_use = not_readmit_ID.sample(n=len(readmit_ID), random_state=1)
id_val_test_t=readmit_ID.sample(frac=0.2,random_state=1)
id_val_test_f=not_readmit_ID_use.sample(frac=0.2,random_state=1)

id_train_t = readmit_ID.drop(id_val_test_t.index)
id_train_f = not_readmit_ID_use.drop(id_val_test_f.index)

id_val_t=id_val_test_t.sample(frac=0.5,random_state=1)
id_test_t=id_val_test_t.drop(id_val_t.index)

id_val_f=id_val_test_f.sample(frac=0.5,random_state=1)
id_test_f=id_val_test_f.drop(id_val_f.index)

# test if there is overlap between train and test, should return "array([], dtype=int64)"
(pd.Index(id_test_t).intersection(pd.Index(id_train_t))).values

id_test = pd.concat([id_test_t, id_test_f])
test_id_label = pd.DataFrame(data = list(zip(id_test, [1]*len(id_test_t)+[0]*len(id_test_f))), columns = ['id','label'])

id_val = pd.concat([id_val_t, id_val_f])
val_id_label = pd.DataFrame(data = list(zip(id_val, [1]*len(id_val_t)+[0]*len(id_val_f))), columns = ['id','label'])

id_train = pd.concat([id_train_t, id_train_f])
train_id_label = pd.DataFrame(data = list(zip(id_train, [1]*len(id_train_t)+[0]*len(id_train_f))), columns = ['id','label'])

#get discharge train/val/test

discharge_train = df_discharge[df_discharge.HADM_ID.isin(train_id_label.id)]
discharge_val = df_discharge[df_discharge.HADM_ID.isin(val_id_label.id)]
discharge_test = df_discharge[df_discharge.HADM_ID.isin(test_id_label.id)]

# subsampling for training....since we obtain training on patient admission level so now we have same number of pos/neg readmission
# but each admission is associated with different length of notes and we train on each chunks of notes, not on the admission, we need
# to balance the pos/neg chunks on training set. (val and test set are fine) Usually, positive admissions have longer notes, so we need
# find some negative chunks of notes from not_readmit_ID that we haven't used yet

df = pd.concat([not_readmit_ID_use, not_readmit_ID])
df = df.drop_duplicates(keep=False)
#check to see if there are overlaps
(pd.Index(df).intersection(pd.Index(not_readmit_ID_use))).values

# for this set of split with random_state=1, we find we need 400 more negative training samples
not_readmit_ID_more = df.sample(n=400, random_state=1)
discharge_train_snippets = pd.concat([df_discharge[df_discharge.HADM_ID.isin(not_readmit_ID_more)], discharge_train])

#shuffle
discharge_train_snippets = discharge_train_snippets.sample(frac=1, random_state=1).reset_index(drop=True)

#check if balanced
discharge_train_snippets.Label.value_counts()

print("BEGINNING SAVING TO CSV")

discharge_train_snippets.to_csv('../data/extended/discharge/train.csv',
                                columns=["SUBJECT_ID","HADM_ID","ADMITTIME","DAYS_NEXT_ADMIT","DAYS_PREV_ADMIT","DURATION","DIAG_ICD9","SMALL_DIAG_ICD9","DIAG_CCS","PROC_ICD9","SMALL_PROC_ICD9","PROC_CCS","NDC","CUI","Label","TEXT","NEXT_SMALL_DIAG_ICD9","NEXT_DIAG_CCS","NEXT_SMALL_PROC_ICD9","NEXT_PROC_CCS","NEXT_CUI"])

discharge_val.to_csv('../data/extended/discharge/val.csv',
                     columns=["SUBJECT_ID","HADM_ID","ADMITTIME","DAYS_NEXT_ADMIT","DAYS_PREV_ADMIT","DURATION","DIAG_ICD9","SMALL_DIAG_ICD9","DIAG_CCS","PROC_ICD9","SMALL_PROC_ICD9","PROC_CCS","NDC","CUI","Label","TEXT","NEXT_SMALL_DIAG_ICD9","NEXT_DIAG_CCS","NEXT_SMALL_PROC_ICD9","NEXT_PROC_CCS","NEXT_CUI"])

discharge_test.to_csv('../data/extended/discharge/test.csv',
                     columns=["SUBJECT_ID","HADM_ID","ADMITTIME","DAYS_NEXT_ADMIT","DAYS_PREV_ADMIT","DURATION","DIAG_ICD9","SMALL_DIAG_ICD9","DIAG_CCS","PROC_ICD9","SMALL_PROC_ICD9","PROC_CCS","NDC","CUI","Label","TEXT","NEXT_SMALL_DIAG_ICD9","NEXT_DIAG_CCS","NEXT_SMALL_PROC_ICD9","NEXT_PROC_CCS","NEXT_CUI"])

### for Early notes experiment: we only need to find training set for 3 days, then we can test
### both 3 days and 2 days. Since we split the data on patient level and experiments share admissions
### in order to see the progression, the 2 days training dataset is a subset of 3 days training set.
### So we only train 3 days and we can test/val on both 2 & 3days or any time smaller than 3 days. This means
### if we train on a dataset with all the notes in n days, we can predict readmissions smaller than n days.

#for 3 days note, similar to discharge

early_train = df_less_3[df_less_3.HADM_ID.isin(train_id_label.id)]
not_readmit_ID_more = df.sample(n=500, random_state=1)
early_train_snippets = pd.concat([df_less_3[df_less_3.HADM_ID.isin(not_readmit_ID_more)], early_train])
#shuffle
early_train_snippets = early_train_snippets.sample(frac=1, random_state=1).reset_index(drop=True)
early_train_snippets.to_csv('../data/extended/3days/train.csv',
                            columns=["SUBJECT_ID","HADM_ID","ADMITTIME","DAYS_NEXT_ADMIT","DAYS_PREV_ADMIT","DURATION","DIAG_ICD9","SMALL_DIAG_ICD9","DIAG_CCS","PROC_ICD9","SMALL_PROC_ICD9","PROC_CCS","NDC","CUI","Label","TEXT","NEXT_SMALL_DIAG_ICD9","NEXT_DIAG_CCS","NEXT_SMALL_PROC_ICD9","NEXT_PROC_CCS","NEXT_CUI"])

early_val = df_less_3[df_less_3.HADM_ID.isin(val_id_label.id)]
early_val.to_csv('../data/extended/3days/val.csv',
                 columns=["SUBJECT_ID","HADM_ID","ADMITTIME","DAYS_NEXT_ADMIT","DAYS_PREV_ADMIT","DURATION","DIAG_ICD9","SMALL_DIAG_ICD9","DIAG_CCS","PROC_ICD9","SMALL_PROC_ICD9","PROC_CCS","NDC","CUI","Label","TEXT","NEXT_SMALL_DIAG_ICD9","NEXT_DIAG_CCS","NEXT_SMALL_PROC_ICD9","NEXT_PROC_CCS","NEXT_CUI"])

# we want to test on admissions that are not discharged already. So for less than 3 days of notes experiment,
# we filter out admissions discharged within 3 days
actionable_ID_3days = df_adm[df_adm['DURATION'] >= 3].HADM_ID
test_actionable_id_label = test_id_label[test_id_label.id.isin(actionable_ID_3days)]
early_test = df_less_3[df_less_3.HADM_ID.isin(test_actionable_id_label.id)]

early_test.to_csv('../data/extended/3days/test.csv',
                  columns=["SUBJECT_ID","HADM_ID","ADMITTIME","DAYS_NEXT_ADMIT","DAYS_PREV_ADMIT","DURATION","DIAG_ICD9","SMALL_DIAG_ICD9","DIAG_CCS","PROC_ICD9","SMALL_PROC_ICD9","PROC_CCS","NDC","CUI","Label","TEXT","NEXT_SMALL_DIAG_ICD9","NEXT_DIAG_CCS","NEXT_SMALL_PROC_ICD9","NEXT_PROC_CCS","NEXT_CUI"])

#for 2 days notes, we only obtain test set. Since the model parameters are tuned on the val set of 3 days

actionable_ID_2days = df_adm[df_adm['DURATION'] >= 2].HADM_ID

test_actionable_id_label_2days = test_id_label[test_id_label.id.isin(actionable_ID_2days)]

early_test_2days = df_less_2[df_less_2.HADM_ID.isin(test_actionable_id_label_2days.id)]

early_test_2days.to_csv('../data/extended/2days/test.csv',
                        columns=["SUBJECT_ID","HADM_ID","ADMITTIME","DAYS_NEXT_ADMIT","DAYS_PREV_ADMIT","DURATION","DIAG_ICD9","SMALL_DIAG_ICD9","DIAG_CCS","PROC_ICD9","SMALL_PROC_ICD9","PROC_CCS","NDC","CUI","Label","TEXT","NEXT_SMALL_DIAG_ICD9","NEXT_DIAG_CCS","NEXT_SMALL_PROC_ICD9","NEXT_PROC_CCS","NEXT_CUI"])
