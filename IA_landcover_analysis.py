
import numpy as np
import rasterio
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

def incangle_dependency(sar_image, incangle, landcover, step=1):

    '''
    Calculates the mean power return in each incidence angle bin and for each land cover class.
    All parameters except for step must be Numpy arrays of the same shape

    Parameters:
        sar_image: np.ndarray, SAR pixels in dB
        incangle: np.ndarray, IA file corregistered to the SAR image
        landcover: np.ndarray, land cover classification raster
        step: int, determines the size of the IA bin
    
    Returns:
        bin_centers: np.ndarray, IA value in the middle of each bin
        landcover_mean_backscatter: dict, keys are the landcover class indices, values are 1-d arrays with mean sigma_0 in each bin
        landcover_pixel_counts: dict, keyr are the landcover class indices, values are the number of pixels of given LC class falling into each IA bin
    '''
    #first bin np.min to 25, last bin 65 to np.max
    bin_edges = np.arange(start=np.nanpercentile(incangle, 2.5), stop=np.nanpercentile(incangle, 97.5), step=np.deg2rad(step))
    bin_edges = np.insert(bin_edges, 0, np.nanmin(incangle))
    bin_edges = np.append(bin_edges, np.nanmax(incangle))

    bin_indices = np.digitize(incangle, bins=bin_edges) #find indices of the array that correspond to each inc. angle bin

    landcover_classes = np.unique(landcover)
    landcover_classes = landcover_classes[landcover_classes>0] #skips zero - denotes no data instead of NaN
    landcover_mean_backscatter = {c: [] for c in landcover_classes}
    landcover_pixel_counts = {c: [] for c in landcover_classes}

    for i in range(1, len(bin_edges)):
        for c in landcover_classes:
            mask = np.logical_and(bin_indices==i, landcover==c) #get mask for current inc. angle and current land cover class
            valid = np.logical_and(mask, ~np.isnan(sar_image))  #only extract non-NaN values
            sar_values = sar_image[valid]
            
            landcover_mean_backscatter[c].append(np.mean(sar_values))
            landcover_pixel_counts[c].append(np.count_nonzero(valid)) #how many valid backscatter values for current inc angle and class

    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    return bin_centers, landcover_mean_backscatter, landcover_pixel_counts

def lc_class_percentage(lc_image, lc_dict):
    '''
    Calculates the percentage that each LC class covers in the AOI.
    
    Parameteres:
        lc_image: np.ndarray, landcover classification raster image
        lc_dict: dict, keys are the integer class descriptors matching lc_image; values are textual descriptions of the classes
    Returns:
        class_percentage: dict, keys are the integer class descriptors; values are the percentages covered by given class
    '''
    a = 0
    class_percentage = {}
    for c in lc_dict.keys():
        #class_mask = np.logical_and(lc==c, ~np.isnan(sar))
        class_mask = lc_image==c
        class_percentage[c] = np.sum(class_mask)/(lc_image.shape[0]*lc_image.shape[1] - np.sum(np.isnan(lc_image))) * 100
        #print(f'{c}: {lc_dict[c]} {np.round(class_percentage[c],2)}%')
        a+=class_percentage[c]

    return class_percentage

def bartsch_lc_classification():
    '''
    Calling this function returns the Bartsch et al. land cover classification description as a dictionary.

    Returns:
        id_to_description: dict, keys (int), values (str)
    '''
    id_to_description = {
    1: "water",
    2: "shallow water / abundant macrophytes",
    3: "wetland, permanent",
    4: "wet to aquatic tundra (seasonal), abundant moss",
    5: "moist to wet tundra, abundant moss, prostrate shrubs",
    6: "dry to moist tundra, partially barren, prostrate shrubs",
    7: "dry tundra, abundant lichen, prostrate shrubs",
    8: "dry to aquatic tundra, dwarf shrubs",
    9: "dry to moist tundra, prostrate to low shrubs",
    10: "moist tundra, abundant moss, prostrate to low shrubs",
    11: "moist tundra, abundant moss, dwarf and low shrubs",
    12: "moist tundra, dense dwarf and low shrubs",
    13: "moist to wet tundra, dense dwarf and low shrubs",
    14: "moist tundra, low shrubs",
    15: "dry to moist tundra, partially barren",
    16: "moist tundra, abundant forbs, dwarf to tall shrubs",
    17: "recently burned or flooded, partially barren",
    18: "forest (deciduous) with dwarf to tall shrubs",
    19: "forest (mixed) with dwarf to tall shrubs",
    20: "forest (needle-leaf) with dwarf and low shrubs",
    21: "partially barren",
    22: "snow / ice",
    23: "other (including shadow)"
    }
    return id_to_description
    
def plot_ia_dependency(inc_angles, lc_bcs, lc_pixel_counts, class_percentage, lc_dict):
    fig, ax = plt.subplots(figsize=(16, 10))
    min_pixels = 1000
    percentage = 0
    for c in lc_bcs.keys():
        if class_percentage[c] < 5: ####plot only classes covering more than 5 percent of the area
            continue
        means = np.array(lc_bcs[c])
        counts = np.array(lc_pixel_counts[c])
        percentage += class_percentage[c]
        valid_mask = counts >= min_pixels
        if np.sum(valid_mask) < 3:
            continue  

        x = np.rad2deg(inc_angles[valid_mask])  #degrees
        y = means[valid_mask]

        #fit a line (degree-1 polynomial)
        slope, intercept = np.polyfit(x, y, deg=1)
        y_fit = slope * x + intercept

        # Calculate R2
        ss_res = np.sum((y - y_fit)**2)
        ss_tot = np.sum((y - np.mean(y))**2)
        r_squared = 1 - (ss_res / ss_tot)

        ax.plot(x, y_fit, label=f'{int(c)} {lc_dict[c]} (slope={slope:.2f}, R2={r_squared:.2f})')

        ax.scatter(x, y, s=10, alpha=0.5)

    ax.set_xlabel("Incidence angle (degrees)")
    ax.set_ylabel("Mean feature value")
    ax.legend(fontsize='large')
    ax.set_title("Incidence angle dependence per land cover class (linear fit)")
    plt.tight_layout()
    plt.grid()
    plt.show()
    print(f'percentage covered by the plotted land cover classes: {percentage}%')