import glob
import csv
import random
from os import path
import os
import bcolz
import sys
import cPickle
import gzip

import numpy as np

from interfaces.data_loader import StandardDataLoader, TRAINING, VALIDATION, TEST, INPUT, OUTPUT, TRAIN
from utils import paths


VALIDATION_SET_SIZE = 0.2


class BcolzAllDataLoader(StandardDataLoader):

    # These are shared between all objects of this type
    labels = dict()
    names = dict()
    spacings = dict()

    datasets = [TRAIN, VALIDATION, TEST]

    def __init__(self, location=paths.ALL_DATA_PATH, *args, **kwargs):
        super(BcolzAllDataLoader, self).__init__(location=location, *args, **kwargs)

    def prepare(self):
        """
        Prepare the dataloader, by storing values to static fields of this class
        In this case, only filenames are loaded prematurely
        :return:
        """
        
        print "previous bcolz nthreads:", bcolz.set_nthreads(1);

        # step 0: load only when not loaded yet
        if TRAINING in self.data and VALIDATION in self.data: return

        # step 1: load the file names
        patients = sorted(glob.glob(self.location+'/*/'))

        print len(patients), "patients"
        # sys.exit()


        labels = dict()
        with open(paths.LABELS_PATH, 'rb') as csvfile:
            reader = csv.reader(csvfile, delimiter=',', quotechar='|')
            next(reader)  # skip the header
            for row in reader:
                labels[str(row[0])] = int(row[1])

        # make a stratified validation set
        # note, the seed decides the validation set, but it is deterministic in the file_names and labels
        random.seed(317070)
        ids_per_label = [[patient_id for patient_id,label in labels.iteritems() if label==l] for l in [0,1]]
        validation_patients = sum([random.sample(sorted(ids), int(VALIDATION_SET_SIZE*len(ids))) for ids in ids_per_label],[])

        # luna_labels = {}
        # with open(paths.LUNA_LABELS_PATH, "rb") as csvfile:
        #     reader = csv.reader(csvfile, delimiter=',', quotechar='|')
        #     next(reader)  # skip the header
        #     for row in reader:
        #         luna_labels[str(row[0])] = diameter_to_prob(float(row[4]))

        # print len(luna_labels)
        # labels.update(luna_labels)

        # make the static data empty
        for s in self.datasets:
            self.data[s] = []
            self.labels[s] = []
            self.names[s] = []
            self.spacings[s] = []

        with gzip.open(paths.SPACINGS_PATH) as f:
            spacings = cPickle.load(f)

        # load the filenames and put into the right dataset
        for i, patient_folder in enumerate(patients):
            patient_id = str(patient_folder.split(path.sep)[-2])
            if patient_id in labels:
                if patient_id in validation_patients:
                    dataset = VALIDATION
                else:
                    dataset = TRAIN
            else:
                dataset = TEST


            self.data[dataset].append(patient_folder)
            if patient_id in labels:
                self.labels[dataset].append(labels[patient_id])
            self.names[dataset].append(patient_id)
            self.spacings[dataset].append(spacings[patient_id])



        print "train", len(self.data[TRAIN])
        print "valid", len(self.data[VALIDATION])
        print "test", len(self.data[TEST])

        # give every patient a unique number
        last_index = -1
        for set in self.datasets:
            self.indices[set] = range(last_index+1,last_index+1+len(self.data[set]))
            if len(self.indices[set]) > 0:
                last_index = self.indices[set][-1]
            print set, len(self.indices[set]), "samples"


    def load_sample(self, sample_id, input_keys_to_do, output_keys_to_do):
        ###################
        #   for testing   #
        ###################
        #sample_id = 1  # test optimizing of parameters
        #import random
        #sample_id = random.choice([1,20000])  # test overfitting

        # find which set this sample is in
        set, set_indices = None, None
        for set, set_indices in self.indices.iteritems():
            if sample_id in set_indices:
                break

        assert sample_id in set_indices, "Sample ID %d is not known in any of the sets?" % sample_id

        sample_index = set_indices.index(sample_id)

        # prepare empty dicts which will contain the result
        sample = dict()
        sample[INPUT] = dict()
        sample[OUTPUT] = dict()

        patient_name = self.names[set][sample_index]
        try:
            volume = bcolz.open(self.data[set][sample_index], 'r')[:].T  # move from zyx to xyz
        except:
            print patient_name
            raise

        # Iterate over input tags and return a dict with the requested tags filled
        for tag in input_keys_to_do:
            tags = tag.split(':')
            if "bcolzall" not in tags: continue

            if "filename" in tags:
                sample[INPUT][tag] = patient_name

            if "3d" in tags or "default" in tags:
                sample[INPUT][tag] = volume

            if "pixelspacing" in tags:
                sample[INPUT][tag] = self.spacings[set][sample_index]  # in mm per pixel

            if "shape" in tags:
                sample[INPUT][tag] = volume.shape

        for tag in output_keys_to_do:
            tags = tag.split(':')
            if "bcolzall" not in tags: continue

            if "target" in tags:
                sample[OUTPUT][tag] = np.int64(self.labels[set][sample_index])

            if "sample_id" in tags:
                sample[OUTPUT][tag] = sample_id

        return sample



# 6% to 28% for nodules 5 to 10 mm,
slope10 = (0.28-0.06) / (10.-5.)
offset10 = 0.06 - slope10*5.
# and 64% to 82% for nodules >20 mm in diameter
slope30 = (0.82-0.64) / (30.-20.)
offset30 = 0.64 - slope30*20.
# For nodules more than 3 cm in diameter, 93% to 97% are malignant
slope40 = (0.97-0.93) / (40.-30.)
offset40 = 0.93 - slope40*30.

def diameter_to_prob(diam):
    # The prevalence of malignancy is 0% to 1% for nodules <5 mm,
    if diam < 5:
        p = 0.01*diam/5.
    elif diam < 10:
        p = slope10*diam+offset10
    elif diam < 20:
        p = (slope10*diam+offset10 + slope30*diam+offset30)/2.
    elif diam < 30:
        p = slope30*diam+offset30
    else:
        p = slope40 * diam + offset40
    return np.clip(p ,0.,1.)


def test_loader():
    # pnts = [diameter_to_prob(i/100.*40.) for i in range(100)]
    # import matplotlib.pyplot as plt
    # plt.plot(pnts)
    # plt.show()

    import utils.plt
    # paths.ALL_DATA_PATH = "/home/lio/data/dsb3/stage1+luna_bcolz/",
    # paths.SPACINGS_PATH =  "/home/lio/data/dsb3/spacings.pkl.gz",
    l = BcolzAllDataLoader(multiprocess=False, location="/home/lio/data/dsb3/stage1+luna_bcolz/")
    l.prepare()
    sample = l.load_sample(l.indices[TRAIN][0], ["bcolzall:3d", "pixelspacing"], ["target"])
    utils.plt.show_animate(sample[INPUT]["bcolzall:3d"], 50)


if __name__ == '__main__':
    test_loader()
