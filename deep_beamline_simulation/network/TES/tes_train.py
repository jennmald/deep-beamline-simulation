from pathlib import Path

import h5py
import numpy as np
import matplotlib.pyplot as plt 
import pandas as pd

import torch
import torch.nn as nn
from torchinfo import summary
from torch.utils.data import DataLoader

from deep_beamline_simulation.u_net import ImageProcessing

import deep_beamline_simulation


def preprocess():
    dbs_init_path = Path(deep_beamline_simulation.__file__)
    print(dbs_init_path)

    dbs_repository_path = dbs_init_path.parent.parent
    print(dbs_repository_path)

    """
    Training data was generated for CSX with a Sirepo ML script.
    """
    # 500 simulations
    train_file = dbs_repository_path / "NSLS-II-TES-beamline-rsOptExport-2/rsopt-srw-20220315141533/datasets/results.h5"

    # read results.h5 generated by Sirepo ML script
    # preprocess the data and write a new h5 file
    with h5py.File(train_file) as f:
        beam_intensities = f["beamIntensities"]
        ip = ImageProcessing(beam_intensities)
        s = ip.smallest_image_size()

        # this is used later
        print(f"params.shape: {f['params'].shape}")
        _parameter_count = f["params"].shape[0]

        # crop the images
        h = beam_intensities.shape[1]
        w = beam_intensities.shape[2]
        hi = 0 + (h // 3)
        hj = h - (h // 3)
        wi = 0 + (w // 3)
        wj = w - (w // 3)

        cropped_beam_intensities = beam_intensities[:, hi:hj, wi:wj]
        plt.figure()
        plt.imshow(beam_intensities[0], aspect="auto")
        plt.title("cropped image")
        plt.show()

        log_cropped_beam_intensities = np.log(cropped_beam_intensities + 1e-10)
        plt.figure()
        plt.hist(log_cropped_beam_intensities.flatten(), bins=100)
        plt.title("log transformed cropped image data")
        plt.show()

        normalized_log_cropped_beam_intensities = (log_cropped_beam_intensities - np.mean(
            log_cropped_beam_intensities)) / np.std(log_cropped_beam_intensities)
        fig, axs = plt.subplots(nrows=1, ncols=2)
        axs[0].hist(normalized_log_cropped_beam_intensities.flatten(), bins=300)
        axs[0].set_title("normalized log transformed cropped image data")

        axs[1].hist(np.std(normalized_log_cropped_beam_intensities, axis=(1, 2)), bins=300)
        axs[1].set_title("std")
        plt.show()

        # this may not be necessary
        bad_image_indices = []
        good_image_indices = []
        resized_images = []

        for i in range(normalized_log_cropped_beam_intensities.shape[0]):
            std = np.std(normalized_log_cropped_beam_intensities[i])
            if 1e-10 < std:
                good_image_indices.append(i)
            else:
                print(f"rejecting image {i} with std {std:.3e}")
                bad_image_indices.append(i)
                # don't plot all bad images, there are about 50
                if len(bad_image_indices) < 3:
                    plt.figure()
                    plt.imshow(
                        ip.resize(
                            normalized_log_cropped_beam_intensities[i],
                            height=128 + 3,
                            length=128 + 1
                        ),
                        aspect="equal"
                    )
                    plt.show()
            resized_images.append(
                ip.resize(
                    normalized_log_cropped_beam_intensities[i],
                    height=128 + 3,
                    length=128 + 1
                )
            )

        print(f"bad image count: {len(bad_image_indices)}")

        initial_beam_intensity_csv_path = dbs_repository_path / "NSLS-II-TES-beamline-rsOptExport-2/tes_init.csv"

        initial_beam_intensity = pd.read_csv(initial_beam_intensity_csv_path, skiprows=1).to_numpy()
        min_initial_beam_intensity = np.min(initial_beam_intensity)
        print(f"min initial beam intensity {min_initial_beam_intensity}")
        if min_initial_beam_intensity > 0:
            e = 0.0
        elif min_initial_beam_intensity == 0.0:
            e = 1e-10
        else:
            e = 1e-10 + np.abs(min_initial_beam_intensity)

        log_initial_beam_intensity = np.log(
            initial_beam_intensity + e
        )
        plt.figure()
        plt.hist(log_initial_beam_intensity.flatten(), bins=100)
        plt.title("log_initial_beam_intensity")
        plt.show()

        normalized_initial_beam_intensity = (log_initial_beam_intensity - np.mean(log_initial_beam_intensity)) / np.std(
            log_initial_beam_intensity)
        resized_initial_beam_intensity = ip.resize(
            normalized_initial_beam_intensity,
            height=128 + 3,
            length=128 + 1
        )

        with h5py.File("preprocessed_results.h5", mode="w") as preprocessed_results:
            good_image_count = len(good_image_indices)

            pi_ds = preprocessed_results.create_dataset(
                "preprocessed_initial_beam_intensity",
                (128, 128)
            )
            pi_ds[:] = resized_initial_beam_intensity

            params_ds = preprocessed_results.create_dataset_like("params", f["params"])
            for i, param in enumerate(f["params"]):
                params_ds[i] = param

            pbi_ds = preprocessed_results.create_dataset(
                "preprocessed_beam_intensities",
                (good_image_count, 128, 128)
            )

            normalized_param_vals_ds = preprocessed_results.create_dataset(
                "preprocessed_param_vals",
                (good_image_count, f["paramVals"].shape[1])
            )

            normalized_param_vals = (f["paramVals"] - np.mean(f["paramVals"])) / np.std(f["paramVals"])
            print(f"normalized_param_vals\n{normalized_param_vals}")

            for i, good_i in enumerate(good_image_indices):
                normalized_param_vals_ds[i] = normalized_param_vals[good_i]
                pbi_ds[i] = resized_images[good_i]

            for good_i in good_image_indices[:10]:
                # print(pbi_ds[i])
                print(f"std: {np.std(pbi_ds[good_i])}")
                f, ax = plt.subplots(nrows=1, ncols=3)
                ax[0].imshow(beam_intensities[good_i], aspect="equal")
                ax[1].imshow(normalized_log_cropped_beam_intensities[good_i], aspect="equal")
                ax[2].imshow(resized_images[good_i], aspect="equal")
                plt.title(f"{params_ds[:]}\n{normalized_param_vals[good_i, :]}")
                plt.show()

        with h5py.File("preprocessed_results.h5", mode="r") as preprocessed_results:
            print(preprocessed_results.keys())
            print(preprocessed_results["params"])
            print(preprocessed_results["params"][:])
            print(preprocessed_results["preprocessed_param_vals"])
            # print(preprocessed_results["preprocessed_initial_beam_intensity"][0:2, :10])

    return _parameter_count, resized_images


def build_beamline_model(parameter_count):
    # build a "down" network, an "up" network, and a "middle" network
    beamline_down = nn.Sequential(
        nn.Conv2d(
            in_channels=1,
            out_channels=16,
            kernel_size=3,
            stride=1,
            padding=1
        ),
        nn.ReLU(),
        nn.Conv2d(
            in_channels=16,
            out_channels=16,
            kernel_size=3,
            stride=1,
            padding=1
        ),
        nn.ReLU(),
        nn.MaxPool2d(
            kernel_size=2,
            stride=2
        ),

        nn.Conv2d(
            in_channels=16,
            out_channels=32,
            kernel_size=3,
            stride=1,
            padding=1
        ),
        nn.ReLU(),
        nn.Conv2d(
            in_channels=32,
            out_channels=32,
            kernel_size=3,
            stride=1,
            padding=1
        ),
        nn.ReLU(),
        nn.MaxPool2d(
            kernel_size=2,
            stride=2
        ),

        nn.Conv2d(
            in_channels=32,
            out_channels=64,
            kernel_size=3,
            stride=1,
            padding=1
        ),
        nn.ReLU(),
        nn.Conv2d(
            in_channels=64,
            out_channels=64,
            kernel_size=3,
            stride=1,
            padding=1
        ),
        nn.ReLU(),
    )
    # output is [*, 32, 32, 32]

    # take four parameters and expand them to a larger layer
    beamline_middle = nn.Sequential(
        nn.Linear(parameter_count, 8),
        nn.ReLU(),
        nn.Linear(8, 64),
        nn.ReLU(),
        nn.Linear(64, 1024),  # for 32x32 filter
        # nn.ReLU()
    )
    # output is [*, 256]

    beamline_up = nn.Sequential(
        nn.ConvTranspose2d(
            in_channels=64 + 1,
            out_channels=32,
            kernel_size=2,
            stride=2,
            padding=0
        ),
        nn.ReLU(),
        nn.Conv2d(
            in_channels=32,
            out_channels=32,
            kernel_size=3,
            stride=1,
            padding=1
        ),
        nn.ReLU(),

        nn.ConvTranspose2d(
            in_channels=32,
            out_channels=16,
            kernel_size=2,
            stride=2,
            padding=0
        ),
        nn.ReLU(),
        nn.Conv2d(
            in_channels=16,
            out_channels=1,
            kernel_size=3,
            stride=1,
            padding=1
        ),
        nn.ReLU(),
        # try ending with conv2d rather than relu to resolve learning failure
        nn.Conv2d(
            in_channels=1,
            out_channels=1,
            kernel_size=3,
            stride=1,
            padding=1
        ),
    )



    class BeamlineModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.parameter_count = parameter_count
            self.beamline_down = beamline_down
            self.beamline_middle = beamline_middle
            self.beamline_up = beamline_up

        def forward(self, image, radius_scale_factor):
            batch_count = image.shape[0]

            down_image_filters = self.beamline_down(image)

            flat_down_image_filters = down_image_filters.reshape(batch_count, -1)

            radius_scale_factor_embedding = self.beamline_middle(radius_scale_factor)

            flat_down_image_filters_with_radius_scale_factor = torch.cat(
                (
                    flat_down_image_filters,
                    radius_scale_factor_embedding
                ),
                dim=1
            )

            image_filters_with_radius_scale_factor = flat_down_image_filters_with_radius_scale_factor.reshape(
                batch_count,
                -1,
                # if the smallest filter is 32x32 the radius scaled factor embedding must be 1024
                32,
                32
            )
            image = self.beamline_up(image_filters_with_radius_scale_factor)

            return image

    return BeamlineModel()


class BeamIntensityDataset:
    def __init__(self, beam_intensities, initial_beam_intensity, params, param_vals):
        self.beam_intensities = np.expand_dims(beam_intensities, axis=1)
        self.initial_beam_intensity = np.expand_dims(initial_beam_intensity, axis=0)
        self.params = params
        self.param_vals = param_vals.astype("float32")

    def __getitem__(self, index):
        return self.beam_intensities[index], self.initial_beam_intensity, self.param_vals[index]

    def __len__(self):
        return self.beam_intensities.shape[0]

    def report(self):
        print(f"length: {len(self)}")
        print(f"initial beam intensity.shape:\n{self.initial_beam_intensity.shape}\n")
        print(f"data shape:\n{self.beam_intensities.shape}\n")
        print(f"data  at index 0:\n{self[0]}\n")
        print(f"beamline parameters dtype:\n\t{self.params.dtype}\n")
        print(f"beamline parameters:\n\t{self.params}\n")


def build_beam_intensity_dataloaders(preprocessed_results_h5_path, batch_size=20):
    with h5py.File(preprocessed_results_h5_path, mode="r") as preprocessed_results:
        initial_beam_intensity_ds = preprocessed_results["preprocessed_initial_beam_intensity"]
        initial_beam_intensity = np.zeros_like(initial_beam_intensity_ds)
        initial_beam_intensity[:] = initial_beam_intensity_ds[:]

        beam_intensities_ds = preprocessed_results["preprocessed_beam_intensities"]
        beam_intensities = np.zeros_like(beam_intensities_ds)
        beam_intensities[:] = beam_intensities_ds[:]

        beamline_parameters_ds = preprocessed_results["params"]
        # this works, but.....
        beamline_parameters = np.zeros_like(beamline_parameters_ds)
        beamline_parameters[:] = beamline_parameters_ds[:]

        beamline_parameter_values_ds = preprocessed_results["preprocessed_param_vals"]
        beamline_parameter_values = np.zeros_like(beamline_parameter_values_ds)
        beamline_parameter_values[:] = beamline_parameter_values_ds[:]

        half = beam_intensities.shape[0] // 2
        two_thirds = 2 * (beam_intensities.shape[0] // 3)

        training_beam_intensity_dataset = BeamIntensityDataset(
            beam_intensities=beam_intensities[:two_thirds],
            initial_beam_intensity=initial_beam_intensity,
            params=beamline_parameters,
            param_vals=beamline_parameter_values[:two_thirds]
        )
        training_beam_intensity_dataloader = DataLoader(
            training_beam_intensity_dataset,
            batch_size=batch_size,
            shuffle=True
        )

        testing_beam_intensity_dataset = BeamIntensityDataset(
            beam_intensities=beam_intensities[two_thirds:],
            initial_beam_intensity=initial_beam_intensity,
            params=beamline_parameters,
            param_vals=beamline_parameter_values[two_thirds:]
        )
        testing_beam_intensity_dataloader = DataLoader(
            testing_beam_intensity_dataset,
            batch_size=batch_size,
            shuffle=True
        )

    return training_beam_intensity_dataloader, testing_beam_intensity_dataloader

def train(
        circle_squasher_model,
        optimizer,
        loss_function,
        train_dataloader,
        test_dataloader,
        epoch_count
):
    training_loss_list = []
    testing_loss_list = []

    if torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    circle_squasher_model.to(device)

    for epoch_i in range(epoch_count):
        training_loss = 0.0
        circle_squasher_model.train()
        for correct_squashed_circle_images, circle_images, radius_scale_factors in train_dataloader:
            optimizer.zero_grad()

            # torch calls circle_images 'inputs'
            circle_images = circle_images.to(device)
            correct_squashed_circle_images = correct_squashed_circle_images.to(device)
            radius_scale_factors = radius_scale_factors.to(device)

            predicted_squashed_circle_images = circle_squasher_model(
                circle_images,
                radius_scale_factors
            )

            loss = loss_function(
                predicted_squashed_circle_images,
                correct_squashed_circle_images
            )
            loss.backward()
            optimizer.step()

            training_loss += loss.data.item()

        training_loss_list.append(training_loss)

        test_loss = 0.0
        circle_squasher_model.eval()
        for correct_squashed_circle_images, circle_images, radius_scale_factors in test_dataloader:
            # torch calls circle_images 'inputs'
            circle_images = circle_images.to(device)
            correct_squashed_circle_images = correct_squashed_circle_images.to(device)
            radius_scale_factors = radius_scale_factors.to(device)

            predicted_squashed_circle_images = circle_squasher_model(
                circle_images,
                radius_scale_factors
            )

            loss = loss_function(predicted_squashed_circle_images, correct_squashed_circle_images)
            test_loss += loss.data.item()

        # test_loss /= len(test_dataloader.dataset)
        testing_loss_list.append(test_loss)

        if epoch_i % 100 == 0:
            print(
                'Epoch: {}, Training Loss: {:.5f}, Test Loss: {:.5f}'.format(
                    epoch_i, training_loss, test_loss
                )
            )

    return training_loss_list, testing_loss_list


_parameter_count, resized_images = preprocess()
summary(
    build_beamline_model(parameter_count=_parameter_count),
    input_data=(torch.ones(2, 1, 128, 128), torch.ones(2, _parameter_count)),
    col_names=("input_size", "output_size", "num_params")
)

training_dataloader, testing_dataloader = build_beam_intensity_dataloaders("preprocessed_results.h5", batch_size=50)
for target_intensities, input_intensities, input_params in training_dataloader:
    print(f"target_intensities.shape : {target_intensities.shape}")
    print(f"input_intensities.shape  : {input_intensities.shape}")
    print(f"input_params.shape       : {input_params.shape}")
    print()
    break
    
for target_intensities, input_intensities, input_params in testing_dataloader:
    print(f"target_intensities.shape : {target_intensities.shape}")
    print(f"input_intensities.shape  : {input_intensities.shape}")
    print(f"input_params.shape       : {input_params.shape}")
    print
    break


def train(
    circle_squasher_model,
    optimizer,
    loss_function,
    train_dataloader,
    test_dataloader,
    epoch_count
):

    training_loss_list = []
    testing_loss_list = []

    if torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    circle_squasher_model.to(device)

    for epoch_i in range(epoch_count):
        training_loss = 0.0
        circle_squasher_model.train()
        for correct_squashed_circle_images, circle_images, radius_scale_factors in train_dataloader:
            optimizer.zero_grad()

            # torch calls circle_images 'inputs'
            circle_images = circle_images.to(device)
            correct_squashed_circle_images = correct_squashed_circle_images.to(device)
            radius_scale_factors = radius_scale_factors.to(device)

            predicted_squashed_circle_images = circle_squasher_model(
                circle_images,
                radius_scale_factors
            )

            loss = loss_function(
                predicted_squashed_circle_images,
                correct_squashed_circle_images
            )
            loss.backward()
            optimizer.step()

            training_loss += loss.data.item()

        #training_loss /= len(train_dataloader.dataset)
        training_loss_list.append(training_loss)
        
        test_loss = 0.0
        circle_squasher_model.eval()
        for correct_squashed_circle_images, circle_images, radius_scale_factors in test_dataloader:

            # torch calls circle_images 'inputs'
            circle_images = circle_images.to(device)
            correct_squashed_circle_images = correct_squashed_circle_images.to(device)
            radius_scale_factors = radius_scale_factors.to(device)

            predicted_squashed_circle_images = circle_squasher_model(
                circle_images,
                radius_scale_factors
            )

            loss = loss_function(predicted_squashed_circle_images, correct_squashed_circle_images)
            test_loss += loss.data.item()

        #test_loss /= len(test_dataloader.dataset)
        testing_loss_list.append(test_loss)

        if epoch_i % 100 == 0:
            print(
                'Epoch: {}, Training Loss: {:.5f}, Test Loss: {:.5f}'.format(
                    epoch_i, training_loss, test_loss
                )
            )

    return training_loss_list, testing_loss_list


# note: restart training if learning is very slow
import torch.optim

simulation_count = len(resized_images)

# batch_size = 5 for TES 500 simulations
beamline = "TES"
train_dataloader, test_dataloader = build_beam_intensity_dataloaders("preprocessed_results.h5", batch_size=50)
epoch_count = 10

print(f"train_dataloader length {len(train_dataloader)}")
print(f"test_dataloader length {len(test_dataloader)}")
beamline_model = build_beamline_model(parameter_count=_parameter_count)
training_loss_list, testing_loss_list = train(
    beamline_model,
    torch.optim.Adam(beamline_model.parameters()),
    torch.nn.MSELoss(),
    train_dataloader,
    test_dataloader,
    epoch_count=epoch_count
)

plt.figure()
plt.plot(training_loss_list, label="training loss")
plt.plot(testing_loss_list, label="testing loss")
plt.title(f"{beamline} {simulation_count} simulations")
plt.xlabel("epoch")
plt.ylabel("loss")
plt.legend()
plt.show()
