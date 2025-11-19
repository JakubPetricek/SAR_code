import os
import subprocess

dem_file = '/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/dem_northslope/elevation.dem'

pols = ['hh', 'vv', 'hv']
segments = [1, 2, 3, 4]
flightline = 'dhorse'
doppler = "dhorse_18517_01_BC.dop"

for pol in pols:
    for seg in segments:
        #pull data that is in the original download format
        print(f'Processing segment s{seg}, polarization {pol}')
        output_dir = os.path.abspath(f'/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/S1_SLC/Pband_InSAR/{flightline}_stack/s{seg}_{pol}')
        input_dir = os.path.abspath(f'/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/S1_SLC/Pband_SLC/{flightline}/{pol}')
        stack_folder = os.path.abspath(f'/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/S1_SLC/Pband_InSAR/{flightline}_stack') #working directory

        #prepare stack    
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        subprocess.run(
            [
                "prepareUAVSAR_coregStack.py",
                "-i", input_dir,
                "-d", doppler,
                "-o", output_dir,
                "-s", str(seg),
            ],
            cwd=stack_folder,
            check=True
        )
        print(f"Data preprocessing done for segment s{seg}, polarization {pol}")
        #folder containing slc data in the right format for stackStripMap.py
        input_slc_folder = f'/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/S1_SLC/Pband_InSAR/{flightline}_stack/s{seg}_{pol}'

        cwd = os.path.abspath(input_slc_folder) #working directory for creating interferograms
        #generate run and config files
        subprocess.run(
                    [
                        "stackStripMap.py",
                        "-s", input_slc_folder,
                        "-d", dem_file,
                        "-a", str(27),
                        "-r", str(7),
                        "--nofocus",
                        "--filter_strength", str(0.2),
                        "-W", "interferogram",
                        "-u", "snaphu",
                        
                    ],
                    cwd=cwd,
                    check=True
                )
        
        config_folder = os.path.join(input_slc_folder, "configs")

        #patch all config_igram_* files beofre running run file 8, the expected paths are wrong so just fix them in the configs
        for fname in os.listdir(config_folder):
            if not fname.startswith("config_igram_"):
                continue

            fpath = os.path.join(config_folder, fname)

            with open(fpath, "r") as f:
                text = f.read()

            #replace '/s1_hh/merged/SLC/<date>/' with '/s1_hh/<date>/'
            text_new = text.replace("/merged/SLC/", "/")

            if text_new != text:
                print(f"Patching {fname}")
                with open(fpath, "w") as f:
                    f.write(text_new)
            else:
                print(f"No change needed for {fname}")

        #run the two necessary run files
        print('Running step TOPO')
        subprocess.run(['run.py', '-i', './run_files/run_01_reference'], cwd=cwd)
        print('Running step IGRAM')
        subprocess.run(['run.py', '-i', './run_files/run_08_igram'], cwd=cwd)

        print(f'Segment {seg} ({pol}) done...')




