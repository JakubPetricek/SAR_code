import os
from mintpy.cli import geocode

flightline = 'dhorse'
pols = ['hh', 'vv', 'hv']

def write_configs(pol, flightline='dhorse'):
    data_dir = f'/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/S1_SLC/Pband_InSAR/{flightline}_stack/mosaic_{pol}'
    #copy baselines folder
    os.system(f'cp -r /Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/S1_SLC/Pband_InSAR/dhorse_stack/s1_{pol}/baselines {data_dir}')
    #create water mask

    smallbaselineApp_config = f"""
mintpy.load.processor        = isce
##---------for ISCE only:
mintpy.load.metaFile         = /Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/S1_SLC/Pband_InSAR/dhorse_stack/s1_{pol}/Igrams/*/referenceShelve/data.dat              
mintpy.load.baselineDir      = {data_dir}/baselines
##---------interferogram datasets:
mintpy.load.unwFile          = {data_dir}/Igrams/*/filt_*.unw
mintpy.load.corFile          = {data_dir}/Igrams/*/filt_*.cor
mintpy.load.connCompFile     = {data_dir}/Igrams/*/filt_*.unw.conncomp
##---------geometry datasets:
mintpy.load.demFile          = {data_dir}/geom_reference/hgt.rdr
mintpy.load.lookupYFile      = {data_dir}/geom_reference/lat.rdr
mintpy.load.lookupXFile      = {data_dir}/geom_reference/lon.rdr
mintpy.load.incAngleFile     = {data_dir}/geom_reference/los.rdr
mintpy.load.azAngleFile      = {data_dir}/geom_reference/los.rdr
mintpy.load.shadowMaskFile   = {data_dir}/geom_reference/shadowMask.rdr
mintpy.load.waterMaskFile    = /Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/S1_SLC/Pband_InSAR/water_mask_dhorse/waterMaskMintPy.rdr

####subset AOI - cut away the empty right half
mintpy.subset.yx = [0:10293, 0:800] #[y0:y1,x0:x1 / no], auto for no

#reference point same as in S1 network
mintpy.reference.lalo          = [69.696529, -148.637519] #[69.717371, -148.705710]

### correct troposphere
mintpy.troposphericDelay.method = pyaps  #[pyaps / height_correlation / gacos / no], auto for pyaps
#mintpy.troposphericDelay.gacosDir = /Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/S1_SLC/orbit_131/stack_3conn_iono/mintpy/GACOS_wide # [path2directory], auto for "./GACOS"

### deramp
## estimate and remove a phase ramp for each acquisition based on the reliable pixels.
## recommended for localized deformation signals, i.e. volcanic deformation, landslide and subsidence, etc.
mintpy.deramp          = linear  #[no / linear / quadratic], auto for no - no ramp will be removed
mintpy.deramp.maskFile = auto  #[filename / no], auto for maskTempCoh.h5, mask file for ramp 

########## 8. correct_topography (optional and recommended)
## Topographic residual (DEM error) correction
## reference: Fattahi and Amelung (2013, IEEE-TGRS)
## stepFuncDate      - Specify stepFuncDate option if you know there are sudden displacement jump in your area,
##    i.e. volcanic eruption, or earthquake, and check timeseriesStepModel.h5 afterward for their estimation.
## excludeDate       - Dates excluded for error estimation only
## pixelwiseGeometry - Use pixel-wise geometry info, i.e. incidence angle and slant range distance
##    yes - use pixel-wise geometry when they are available [slow; used by default]
##    no  - use mean geometry [fast]
mintpy.topographicResidual                   = yes  #[yes / no], auto for yes
mintpy.topographicResidual.polyOrder         = auto  #[1-inf], auto for 2, poly order of temporal deformation model
mintpy.topographicResidual.phaseVelocity     = auto  #[yes / no], auto for no - phase, use phase velocity for minimization
mintpy.topographicResidual.stepFuncDate      = auto  #[20080529,20100611 / no], auto for no, date of step jump
mintpy.topographicResidual.excludeDate       = auto  #[20070321 / txtFile / no], auto for exclude_date.txt
mintpy.topographicResidual.pixelwiseGeometry = auto  #[yes / no], auto for yes, use pixel-wise geometry info
"""

    path_mintpy_dir = os.path.join(data_dir, 'mintpy', 'mintpy_config.txt')
    with open(path_mintpy_dir, 'w') as f:
        f.write(smallbaselineApp_config)
    

#process each polarization channel
for pol in pols:

    mintpy_dir = f'/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/S1_SLC/Pband_InSAR/{flightline}_stack/mosaic_{pol}/mintpy'
    os.makedirs(mintpy_dir, exist_ok=True)
    os.chdir(mintpy_dir)
    
    #write config file used in processing
    write_configs(pol, flightline=flightline)
    #step 1: load data and extract water mask
    os.system('smallbaselineApp.py mintpy_config.txt --dostep load_data')
    os.system('generate_mask.py inputs/geometryRadar.h5 waterMask --nonzero -o waterMask.h5')
    
    #SBAS network inversion
    os.system('smallbaselineApp.py mintpy_config.txt --start modify_network --end invert_network')
    print('Network inversion done.')
    print("Doing the following corrections: tropo, deramp, DEM.")
    #apply corrections
    os.system('smallbaselineApp.py mintpy_config.txt --start correct_troposphere --end correct_topography')
   
    #geocoding coherence, deformation timeseries, masks
    geocode.main('inputs/ifgramStack.h5 -d coherence --lalo 0.0001388888888888889 0.0001388888888888889 --outdir ./geo/'.split())
    geocode.main('waterMask.h5 --lalo 0.0001388888888888889 0.0001388888888888889 --outdir ./geo/'.split())
    geocode.main('maskTempCoh.h5 --lalo 0.0001388888888888889 0.0001388888888888889 --outdir ./geo/'.split())
    geocode.main('timeseries_ERA5_ramp_demErr.h5 -d timeseries --lalo 0.0001388888888888889 0.0001388888888888889 --outdir ./geo/'.split())

    print(f"Time series processing done for {pol.upper()}!")

