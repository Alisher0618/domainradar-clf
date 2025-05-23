"""
Phishing CNN classifier for DomainRadar

The classifier uses a convolution neural network (CNN) model to classify phishing
domain names. Feature values are transformed into a 2D matrix which is then
processed by the model and its convolution layers.
"""

__authors__ = [
    "Jan Polisensky (model definition & training)",
    "Radek Hranicky (supporting class, testing, integration)",
]

import math
import os

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
import joblib
from pandas import DataFrame

from .models.phishing_cnn_model_net import Net as Phishing_CNN_Net
from .options import PipelineOptions

from sklearn.preprocessing import MinMaxScaler
from classifiers.options import PipelineOptions


from pandas.core.dtypes import common as com
import tensorflow as tf
from tensorflow.keras.models import load_model


class Clf_phishing_cnn:
    """
    Class for the CNN phishing classifier.
    Expects the model loaded in the ./models/ directory.
    Use the `classify` method to classify a dataset of domain names.
    """

    def __init__(self, options: PipelineOptions):
        """
        Initializes the classifier.
        """

        self.device = torch.device("cpu")  # Production environment uses CPU
        self.base_dir = os.path.dirname(__file__)
        self.scaler = joblib.load(
            os.path.join(options.boundaries_dir, "phishing_cnn_scaler.joblib")
        )

        # The number of features in the feature vector
        # IMPORTANT: EDIT THIS if the model is changed!
        self.feature_size = 173

        # Calculate the sizes and padding of the NN model
        self.desired_size = self.next_perfect_square(self.feature_size)
        self.side_size = int(self.desired_size**0.5)
        self.padding = self.desired_size - self.feature_size

        # Load and evaluate the model
        self.state_dict = torch.load(
            os.path.join(options.models_dir, "phishing_cnn_model_state_dict.pth"),
            map_location=self.device,
        )
        self.model = Phishing_CNN_Net(self.side_size).to(self.device)
        self.model.load_state_dict(self.state_dict)
        self.model.eval()

        self.disqualified_columns = [
            "tls_joint_isoitu_policy_crt_count",
            "rdap_time_from_last_change",
            "lex_www_flag",
        ]

    def cast_timestamp(self, df: DataFrame):
        """
        Cast timestamp fields to seconds since epoch.
        """
        for col in df.columns:
            if com.is_timedelta64_dtype(df[col]):
                df[col] = df[
                    col
                ].dt.total_seconds()  # This converts timedelta to float (seconds)
            elif com.is_datetime64_any_dtype(df[col]):
                df[col] = (
                    df[col].astype(np.int64) // 10**9
                )  # Converts datetime64 to Unix timestamp (seconds)

        return df

    def next_perfect_square(self, n):
        """
        Calculates the next perfect square greater than a given number
        """
        next_square = math.ceil(n**0.5) ** 2
        return next_square

    def classify(self, feature_vectors: DataFrame) -> list:
        input_data = feature_vectors.copy()

        # Remove disqualified columns
        for column in self.disqualified_columns:
            if column in input_data.columns:
                input_data.drop(column, axis=1, inplace=True)

        # Remove html_ columns (current model does not support them) !
        input_data = input_data[[col for col in input_data.columns if not col.startswith('html_')]]

        # Drop the 'domain_name' column if it exists
        if "domain_name" in input_data.columns:
            input_data = input_data.drop("domain_name", axis=1)

        # Drop the 'label' column if it exists
        if "label" in input_data.columns:
            input_data = input_data.drop("label", axis=1)

        # Cast timestamps
        input_data = self.cast_timestamp(input_data)

        # Handle NaNs
        input_data.fillna(-1, inplace=True)

        # Scale the feature matrix using the loaded scaler
        input_data = self.scaler.transform(input_data)

        # transform input data to tensor
        input_data = torch.tensor(input_data, dtype=torch.float32)

        # Verify if the shape is correct
        if input_data.shape[1] != self.feature_size:
            raise Exception(
                "The number of features in the input data does not match the expected size!"
            )

        if self.padding > 0:
            data_tensor_padded = F.pad(input_data, (0, self.padding), "constant", 0)
        else:
            data_tensor_padded = input_data

        data_tensor_reshaped = data_tensor_padded.view(
            -1, 1, self.side_size, self.side_size
        )
        data_tensor_reshaped = data_tensor_reshaped.to(self.device)

        with torch.no_grad():
            outputs = self.model(data_tensor_reshaped)
            outputs_cpu = torch.sigmoid(outputs).cpu().numpy()

        return outputs_cpu
