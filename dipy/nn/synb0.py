#!/usr/bin/python
"""
Class and helper functions for fitting the Synb0 model.
"""


from packaging.version import Version
import logging
from dipy.data import get_fnames
from dipy.testing.decorators import doctest_skip_parser
from dipy.utils.optpkg import optional_package
import numpy as np

tf, have_tf, _ = optional_package('tensorflow')
tfa, have_tfa, _ = optional_package('tensorflow_addons')
if have_tf and have_tfa:
    import tensorflow as tf
    import tensorflow_addons as tfa
    if Version(tf.__version__) < Version('2.0.0'):
        raise ImportError('Please upgrade to TensorFlow 2+')

logging.basicConfig()
logger = logging.getLogger('synb0')


def set_logger_level(log_level):
    """ Change the logger of the Synb0 to one on the following:
    DEBUG, INFO, WARNING, CRITICAL, ERROR

    Parameters
    ----------
    log_level : str
        Log level for the Synb0 only
    """
    logger.setLevel(level=log_level)


class Synb0():
    """
    This class is intended for the Synb0 model.
    """

    @doctest_skip_parser
    def __init__(self, verbose=False):
        r"""
        The model was pre-trained for usage on pre-processed images following the synb0-disco pipeline

        To obtain the pre-trained model, use::
        >>> synb0_model = Synb0() # skip if not have_tf
        >>> fetch_model_weights_path = get_fnames('synb0_default_weights') # skip if not have_tf
        >>> synb0_model.load_model_weights(fetch_model_weights_path) # skip if not have_tf

        This model is designed to take as input a b0 image and a T1 weighted image.
        It was designed to predict a b-inf image.

        Parameters
        ----------
        verbose : bool (optional)
            Whether to show information about the processing.
            Default: False

        References
        ----------
        ..  [1] Schilling, K. G., Blaber, J., Huo, Y., Newton, A., 
            Hansen, C., Nath, V., ... & Landman, B. A. (2019).
            Synthesized b0 for diffusion distortion correction (Synb0-DisCo).
            Magnetic resonance imaging, 64, 62-70.
        ..  [2] Schilling, K. G., Blaber, J., Hansen, C., Cai, L., 
            Rogers, B., Anderson, A. W., ... & Landman, B. A. (2020).
            Distortion correction of diffusion weighted MRI without reverse
            phase-encoding scans or field-maps.
            PloS one, 15(7), e0236418.
        """

        if not have_tf:
            raise tf()

        log_level = 'INFO' if verbose else 'CRITICAL'
        set_logger_level(log_level)

        # Synb0 network load

        self.model = UNet3D()
        self.model.build(input_shape=(None, 80, 96, 80, 2))
        class UNet3D(tf.keras.Model):
            def __init__(self):
                super(UNet3D, self).__init__()
                # Encoder
                self.ec0 = self.encoder_block(32, kernel_size=3, stride=1, padding='same')
                self.ec1 = self.encoder_block(64, kernel_size=3, stride=1, padding='same')
                self.pool0 = tf.keras.layers.MaxPool3D()
                self.ec2 = self.encoder_block(64, kernel_size=3, stride=1, padding='same')
                self.ec3 = self.encoder_block(128, kernel_size=3, stride=1, padding='same')
                self.pool1 = tf.keras.layers.MaxPool3D()
                self.ec4 = self.encoder_block(128, kernel_size=3, stride=1, padding='same')
                self.ec5 = self.encoder_block(256, kernel_size=3, stride=1, padding='same')
                self.pool2 = tf.keras.layers.MaxPool3D()
                self.ec6 = self.encoder_block(256, kernel_size=3, stride=1, padding='same')
                self.ec7 = self.encoder_block(512, kernel_size=3, stride=1, padding='same')
                self.pool2 = tf.keras.layers.MaxPool3D()
                self.el = tf.keras.layers.Conv3D(512, kernel_size=1, stride=1, padding='same')

                # Decoder
                self.dc9 = self.decoder_block(512, kernel_size=2, stride=2, padding='valid')
                self.dc8 = self.decoder_block(256, kernel_size=3, stride=1, padding='same')
                self.dc7 = self.decoder_block(256, kernel_size=3, stride=1, padding='same')
                self.dc6 = self.decoder_block(256, kernel_size=2, stride=2, padding='valid')
                self.dc5 = self.decoder_block(128, kernel_size=3, stride=1, padding='same')
                self.dc4 = self.decoder_block(128, kernel_size=3, stride=1, padding='same')
                self.dc3 = self.decoder_block(128, kernel_size=2, stride=2, padding='valid')
                self.dc2 = self.decoder_block(64, kernel_size=3, stride=1, padding='same')
                self.dc1 = self.decoder_block(64, kernel_size=3, stride=1, padding='same')
                self.dc0 = self.decoder_block(1, kernel_size=1, stride=1, padding='valid')
                self.dl = tf.keras.layers.Conv3DTranspose(1, kernel_size=1, stride=1, padding='valid')
            def call(self, input):
                # Encode
                x = self.ec0(input)
                syn0 = self.ec1(x)

                x = self.pool0(syn0)
                x = self.ec2(x)
                syn1 = self.ec3(x)

                x = self.pool1(syn1)
                x = self.ec4(x)
                syn2 = self.ec5(x)                

                x = self.pool2(syn2)
                x = self.ec6(x)
                x = self.ec7(x)

                # Last layer without relu
                x = self.el(x)

                x = tf.keras.layers.Concatenate()([self.dc9(x), syn2])

                x = self.dc8(x)
                x = self.dc7(x)

                x = tf.keras.layers.Concatenate()([self.dc6(x), syn1])

                x = self.dc5(x)
                x = self.dc4(x)

                x = tf.keras.layers.Concatenate()([self.dc3(x), syn0])

                x = self.dc2(x)
                x = self.dc1(x)

                x = self.dc0(x)

                # Last layer without relu
                out = self.dl(x)

                return out

            class encoder_block(tf.keras.layers.Layer):
                def __init__(self, out_channels, kernel_size, stride, padding):
                    super(UNet3D.encoder_block, self).__init__()
                    self.conv3d = tf.keras.layers.Conv3D(out_channels, kernel_size, strides=stride, padding=padding, use_bias=False)
                    self.instnorm = tfa.layers.InstanceNormalization(out_channels)
                    self.activation = tf.keras.layers.LeakyReLU(0.01)
                def call(self, input):
                    x = self.conv3d(input)
                    x = self.instnorm(x)
                    x = self.activation(x)

                    return x
            
            class decoder_block(tf.keras.layers.Layer):
                def __init__(self, out_channels, kernel_size, stride, padding):
                    super(UNet3D.decoder_block, self).__init__()
                    self.conv3d = tf.keras.layers.Conv3DTranspose(out_channels, kernel_size, strides=stride, padding=padding, use_bias=False)
                    self.instnorm = tfa.layers.InstanceNormalization(out_channels)
                    self.activation = tf.keras.layers.LeakyReLU(0.01)
                def call(self, input):
                    x = self.conv3d(input)
                    x = self.instnorm(x)
                    x = self.activation(x)

                    return x



            
    
    def fetch_default_weights(self):
        r"""
        Load the model pre-training weights to use for the fitting.
        """
        fetch_model_weights_path = get_fnames('synb0_default_weights')
        self.load_model_weights(fetch_model_weights_path)

    def load_model_weights(self, weights_path):
        r"""
        Load the custom pre-training weights to use for the fitting.

        Parameters
        ----------
        weights_path : str
            Path to the file containing the weights (hdf5, saved by tensorflow)
        """
        try:
            self.model.load_weights(weights_path)
        except ValueError:
            raise ValueError('Expected input for the provided model weights do not match the declared model')

    def __predict(self, x_test):
        r"""
        Reconstruct b-inf image(s)

        Parameters
        ----------
        x_test : np.ndarray (batch, 80, 96, 80, 2)
            Image should match the required shape of the model.

        Returns
        -------
        np.ndarray (...) or (batch, ...)
            Reconstructed b-inf image(s)
        """
    
        return self.model.predict(x_test)[..., 0]
    
    def __normalize(self, image, max_img, min_img):
        r"""
        Internal normalization function

        Parameters
        ----------
        image : np.ndarray

        Returns
        -------
        np.ndarray
            Normalized image from range -1 to 1
        """
        return (((image - min_img)/(max_img - min_img))-0.5)*2

    def __unnormalize(self, image, max_img, min_img):
        r"""
        Internal unnormalization function

        Parameters
        ----------
        image : np.ndarray

        Returns
        -------
        np.ndarray
            unnormalized image from range min_img to max_img
        """
        return (image+1)/2*(max_img-min_img) + min_img
            

    def predict(self, b0, T1, batch_size=None):
        r"""
        Wrapper function to faciliate prediction of larger dataset.
        The function will scale the data to meet the required shape of image.

        Parameters
        ----------
        b0 : np.ndarray (batch, 77, 91, 77) or (77, 91, 77)
            For a single image, input should be a 3D array. If multiple images, there should also be a batch dimension
        
        T1 : np.ndarray (batch, 77, 91, 77) or (77, 91, 77)
            For a single image, input should be a 3D array. If multiple images, there should also be a batch dimension

        batch_size : int
            Number of images per prediction pass. Only available if data is provided with a batch dimension.
            Consider lowering it if you get an out of memory error. Increase it if you want it to be faster.
            If None, batch_size will set to be 1 if the provided image has a batch dimension
            Default is None
        Returns
        -------
        pred_output : np.ndarray (...) or (batch, ...)
            Reconstructed b-inf image(s)
            
        """
        if all([b0.shape[1:]!=(77, 91, 77), b0.shape!=(77, 91, 77)]) or \
            b0.shape != T1.shape:
            raise ValueError('Expected shape (batch, 77, 91, 77) or (77, 91, 77) on the inputs do not match the shape of the inputs')
        
        shape = b0.shape
        dim = len(shape)

        if dim == 3:
            T1 = np.pad(T1, ((2, 1), (3, 2), (2, 1)), 'constant')
            b0 = np.pad(b0, ((2, 1), (3, 2), (2, 1)), 'constant')
            p99 = np.percentile(b0, 99)
            T1 = self.__normalize(T1, 150, 0)
            b0 = self.__normalize(b0, p99, 0)
        else:
            T1 = np.pad(T1, ((0, 0), (2, 1), (3, 2), (2, 1)), 'constant')
            b0 = np.pad(b0, ((0, 0), (2, 1), (3, 2), (2, 1)), 'constant')
            p99 = np.percentile(b0, 99, axis=(1, 2, 3))
            for i in range(shape[0]):
                T1[i] = self.__normalize(T1[i], 150, 0)
                b0[i] = self.__normalize(b0[i], p99[i], 0)

        if dim == 3:
            if batch_size is not None:
                logger.warning('Batch size was specified, but was not used',
                'due to the input not having a batch dimension')
            input_data = np.expand_dims(np.concatenate([b0, T1], -1), 0)
            prediction = self.__predict(input_data)
            prediction = self.__unnormalize(prediction, p99, 0)
            prediction = prediction[0, 2:-1, 3:-2, 2:-1, 0]

        else:
            if batch_size is None:
                batch_size = 1
            input_data = np.concatenate([b0, T1], -1)
            prediction = np.zeros(shape+(1,))
            for batch_idx in range(batch_size, shape[0]+1, batch_size):
                prediction[:batch_idx] = self.__predict(input_data)
            if np.mod(shape[0], batch_size) != 0:
                prediction[-np.mod(shape[0], batch_size):] = self.__predict(input_data)
            for i in range(shape[0]):
                prediction[i] = self.__unnormalize(prediction[i], p99[i], 0)
            prediction = prediction[:, 2:-1, 3:-2, 2:-1]
        
        return prediction

            
