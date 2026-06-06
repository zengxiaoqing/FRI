# -*- coding: utf-8 -*- 
# cython:language_level=3

# import warnings
# warnings.simplefilter(action='ignore', category=(FutureWarning, RuntimeWarning))
import os
import sys
import h5py
import time
import datetime
import argparse
import configparser
import numpy as np
import pandas as pd
from multiprocessing  import cpu_count
import Module_Interp_dem6 as MInterp3d


#主程序
if __name__ == '__main__':

  #当前路径
  scurrent_path = os.getcwd()
  
  #引入模块
  cls_itp3d = MInterp3d.Class_Interp_dem(iDebug=0)
  
  #指定地形插值瞬时要素名
  cls_itp3d.ltPQ_FRI_Inst = ['2t', '2rh', '10u', '10v', '10ws', 'sp'] #6个  风速'10u', '10v', '10ws'
  #指定模式
  sModel_Region_upper="CMA_12P5KM" #EC_12P5KM
  
  
  #-------------------------------------------------------------
  #要插值的目标信息(这里以站点为例)
  #读取站点信息
  sIn_abs_path=os.path.join(scurrent_path,"Station1")
  dtsite = cls_itp3d.dRead_Station_Info(sIn_abs_path)
  #排除模式数据区域外站点
  ltSlt_Site_Code=[];ltSlt_Site_Lon=[];ltSlt_Site_Lat=[];ltSlt_Site_Alt=[]
  for scode in dtsite:
    ltSlt_Site_Code.append(scode)
    ltSlt_Site_Lon.append(dtsite[scode][1])
    ltSlt_Site_Lat.append(dtsite[scode][2])
    ltSlt_Site_Alt.append(dtsite[scode][3])
  #目标插值结果的地理空间信息
  dyIntp_info={"site":None}
  sReso_dir="Site"
  #站点插值经纬度海拔信息
  dyIntp_info["site"]={"lon" :np.array(ltSlt_Site_Lon),
                       "lat" :np.array(ltSlt_Site_Lat),
                       "alt" :np.array(ltSlt_Site_Alt),
                       "size":len(ltSlt_Site_Code),
                       "dir" :sReso_dir,
                       "code":ltSlt_Site_Code,
                       "file":sIn_abs_path}
  #--------------------------------------------------------------
  
  
  #-------------------------------------------------------------
  #读模式原始数据
  if sModel_Region_upper=="EC_12P5KM":

    #模式近地面单层变量
    ltSPQ_shortname  = ["10u","10v","10fg3","2t","mn2t3","mx2t3","2d","sp"]
    #模式多层变量
    ltMPQ_shortname  = ["gh","t","u","v","q","r"]
    #读取EC模式GRIB数据
    sIn_dmo_filename = "2024072412_009_C1D07241200072421001"
    sIn_dmo_abspath  = os.path.join(scurrent_path,sIn_dmo_filename)
    dymdl_rdata = cls_itp3d.dRGrib_EC(sIn_dmo_abspath, ltSPQ_shortname, ltMPQ_shortname)
  else:
    #读数据
    #模式近地面单层变量
    ltSPQ_shortname  = ["10u","10v","gust","2t","tmin","tmax","2r","2r_max","2r_min","sp"]
    #模式多层变量
    ltMPQ_shortname  = ["gh","t","u","v","q","r"]
    #读取cma模式GRIB数据
    sIn_dmo_filename = "gmf.gra.2024072412009.grb2"
    sIn_dmo_abspath  = os.path.join(scurrent_path,sIn_dmo_filename)
    dymdl_rdata = cls_itp3d.dRGrib_EC(sIn_dmo_abspath, ltSPQ_shortname, ltMPQ_shortname)
    #2t,10u,10v,tmax,tmin,sp,gh,t,u,v,r,2rh,10gust
  #-------------------------------------------------------------

  
  #--------------------------------------------------------------
  #模式信息
  if sModel_Region_upper in ["EC_12P5KM","EC"]:
    #读取模式近地面数据对应的海拔数据
    stif_abs_path  = os.path.join(scurrent_path,"EC_Terrain_12P5km.tif")
    ndyterrain_mdl = cls_itp3d.dRead_Terrain(stif_abs_path) #返回一个numpy n-d数组 上-下(北-南) 左-右(西-东)
    #模式近地面层经纬度信息(左-右:西-东 上-下:南-北)
    dylonlat_SL_IG_mdl={"begin_lon":70,
                        "end_lon"  :140,
                        "begin_lat":0,
                        "end_lat"  :60,
                        "lon_res"  :0.125,  "lat_res"  :0.125}
    dylonlat_SL_IG_mdl=cls_itp3d.dlonlat_info(dylonlat_SL_IG_mdl, around=3, idebug=0, slabel="EC_SL_DMO")
    #EC多层智网范围的25k地理信息
    dylonlat_ML_IG_mdl={"begin_lon":70,
                        "end_lon"  :140,
                        "begin_lat":0,
                        "end_lat"  :60,
                        "lon_res"  :0.25, "lat_res"  :0.25} #=481×561
    #(EC多层: 左-右:西-东 上-下:南-北)
    dylonlat_ML_IG_mdl=cls_itp3d.dlonlat_info(dylonlat_ML_IG_mdl, around=2,idebug=0,slabel="EC_ML_DMO")
    #找出在12.5km数据中的25km公共索引(1维数组)
    mask2d_x_lon_12P5km_to_25km=np.in1d(dylonlat_SL_IG_mdl["ndy2d_x_lon"].flatten(),dylonlat_ML_IG_mdl["ndy1d_x_lon"].flatten()) #返回一个与ar1长度相同的布尔数组,ar1的元素在ar2中=True
    #返回一个与ar1长度相同的布尔数组,ar1的元素在ar2中=True
    mask2d_y_lat_12P5km_to_25km=np.in1d(dylonlat_SL_IG_mdl["ndy2d_y_lat"].flatten(),dylonlat_ML_IG_mdl["ndy1d_y_lat"].flatten()) #42607100个点=1维
    #在原12.5km数据中,与25km数据公共部分点的布尔索引  
    mask2d_common_12P5km_to_25km = (mask2d_y_lat_12P5km_to_25km * mask2d_x_lon_12P5km_to_25km).reshape(dylonlat_SL_IG_mdl["tpshape_lonlat"]) #与1km保持一致,6001*7100=42607100个点 True/False
    #保存数据
    dylonlat_SL_IG_mdl["alt"]                  = ndyterrain_mdl       #上-下(南-北)
    dylonlat_SL_IG_mdl["size"]                 = dylonlat_SL_IG_mdl["ndy2d_x_lon"].size
    dymdl_Geog                                 = {}
    dymdl_Geog["lonlat_SL_IG_mdl"]             = dylonlat_SL_IG_mdl   #EC:0-60.0  CMA-GFS:0.12-60.125 和 0.0625-60.0625
    dymdl_Geog["lonlat_ML_IG_mdl"]             = dylonlat_ML_IG_mdl
    dymdl_Geog["mask2d_common_12P5km_to_25km"] = mask2d_common_12P5km_to_25km
  elif sModel_Region_upper in ["GRAPES_12P5KM","GRAPES_GFS","CMA_GFS","CMA_12P5KM"]:
    #读取模式近地面数据对应的海拔数据
    stif_abs_path  = os.path.join(scurrent_path,"CMA_Terrain_12P5km.tif")
    ndyterrain_mdl = cls_itp3d.dRead_Terrain(stif_abs_path) #返回一个numpy n-d数组 上-下(北-南) 左-右(西-东)
    #模式近地面层经纬度信息(左-右:西-东 上-下:南-北)
    dylonlat_SL_IG_mdl={"begin_lon":70,
                        "end_lon"  :140,
                        "begin_lat":0.0625,
                        "end_lat"  :60.0625,
                        "lon_res"  :0.125,  "lat_res"  :0.125}
    dylonlat_SL_IG_mdl=cls_itp3d.dlonlat_info(dylonlat_SL_IG_mdl, around=3, idebug=0, slabel="EC_SL_DMO")
    #保存数据
    dylonlat_SL_IG_mdl["alt"]                  = ndyterrain_mdl       #上-下(南-北)
    dylonlat_SL_IG_mdl["size"]                 = dylonlat_SL_IG_mdl["ndy2d_x_lon"].size
    dymdl_Geog                                 = {}
    dymdl_Geog["lonlat_SL_IG_mdl"]             = dylonlat_SL_IG_mdl
    dymdl_Geog["lonlat_ML_IG_mdl"]             = None
    dymdl_Geog["mask2d_common_12P5km_to_25km"] = None
    #--------------------------------------------------------------

  #地形插值
  if sModel_Region_upper in ["EC_12P5KM","EC"]:
    dyIntp_rlt = cls_itp3d.dECDMO_3d_Interp_nPQ(dymdl_rdata, dymdl_Geog, dyIntp_info)
  elif sModel_Region_upper in ["GRAPES_12P5KM","GRAPES_GFS","CMA_GFS","CMA_12P5KM"]:
    print("a")
    dyIntp_rlt = cls_itp3d.dCMADMO_3d_Interp_nPQ(dymdl_rdata, dymdl_Geog, dyIntp_info)
    

  # #---------------------------写数据--------------------------------------------
  # sIn_abs_path=os.path.join(scurrent_path,"out.h5")
  # cls_itp3d.dWS3_Interp(sIn_abs_path, dyIntp_rlt["site"])