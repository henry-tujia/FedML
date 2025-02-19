import logging

import numpy as np
from PIL import Image
from torchvision.datasets import DatasetFolder
import torch.utils.data as data
import six
import lmdb
import os
import pickle

# logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

IMG_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.ppm', '.bmp',
                  '.pgm', '.tif', '.tiff', '.webp')


def accimage_loader(path):
    import accimage
    try:
        return accimage.Image(path)
    except IOError:
        # Potentially a decoding problem, fall back to PIL.Image
        return pil_loader(path)


def pil_loader(path):
    # open path as file to avoid ResourceWarning (https://github.com/python-pillow/Pillow/issues/835)
    with open(path, 'rb') as f:
        img = Image.open(f)
        return img.convert('RGB')


def default_loader(path):
    from torchvision import get_image_backend
    if get_image_backend() == 'accimage':
        return accimage_loader(path)
    else:
        return pil_loader(path)


class ImageFolderTruncated(DatasetFolder):
    """A generic data loader where the images are arranged in this way: ::

        root/dog/xxx.png
        root/dog/xxy.png
        root/dog/xxz.png

        root/cat/123.png
        root/cat/nsdf3.png
        root/cat/asd932_.png

    Args:
        root (string): Root directory path.
        transform (callable, optional): A function/transform that  takes in an PIL image
            and returns a transformed version. E.g, ``transforms.RandomCrop``
        target_transform (callable, optional): A function/transform that takes in the
            target and transforms it.
        loader (callable, optional): A function to load an image given its path.
        is_valid_file (callable, optional): A function that takes path of an Image file
            and check if the file is a valid_file (used to check of corrupt files)

     Attributes:
        classes (list): List of the class names.
        class_to_idx (dict): Dict with items (class_name, class_index).
        imgs (list): List of (image path, class_index) tuples
    """

    def __init__(self, root, dataidxs=None, transform=None, target_transform=None,
                 loader=default_loader, is_valid_file=None):
        super(ImageFolderTruncated, self).__init__(root, loader, IMG_EXTENSIONS if is_valid_file is None else None,
                                                   transform=transform,
                                                   target_transform=target_transform,
                                                   is_valid_file=is_valid_file)
        self.imgs = self.samples
        self.dataidxs = dataidxs

        # we need to fetch training labels out here:
        self._train_labels = np.array([tup[-1] for tup in self.imgs])

        self.__build_truncated_dataset__()

    def __build_truncated_dataset__(self):
        if self.dataidxs is not None:
            # self.imgs = self.imgs[self.dataidxs]
            self.imgs = [self.imgs[idx] for idx in self.dataidxs]

    def __len__(self):
        return len(self.imgs)

    def __getitem__(self, index):
        """
        Args:
            index (int): Index

        Returns:
            tuple: (sample, target) where target is class_index of the target class.
        """
        path, target = self.imgs[index]
        sample = self.loader(path)
        if self.transform is not None:
            sample = self.transform(sample)
        else:
            sample = np.array(sample)
        if self.target_transform is not None:
            target = self.target_transform(target)
        return sample, target

    @property
    def get_train_labels(self):
        return self._train_labels


def loads_data(buf):
    """
    Args:
        buf: the output of `dumps`.
    """
    return pickle.loads(buf)


class ImageFolderLMDB(data.Dataset):
    def __init__(self, db_path, transform=None, target_transform=None,dataidxs=None):
        self.db_path = db_path+".lmdb"
        self.env = lmdb.open(self.db_path, subdir=os.path.isdir(self.db_path),
                             readonly=True, lock=False,
                             readahead=False, meminit=False)

        with self.env.begin(write=False) as txn:
            self.length = loads_data(txn.get(b'__len__'))
            self.keys = dict(loads_data(txn.get(b'__keys__')))
        self.dataidxs = dataidxs
        self.get_imgs()
        self.targets = list(self.keys.values())
        self.transform = transform
        self.target_transform = target_transform
        
    def get_imgs(self):
        if self.dataidxs is not None:
            self.imgs = self.dataidxs
        else:
            self.imgs = np.array(list(self.keys.keys()),dtype=int)

    def __getitem__(self, index):
        env = self.env
        with env.begin(write=False) as txn:
            idx = self.imgs[index]
            byteflow = txn.get(u'{}'.format(idx).encode('ascii'))

        unpacked = loads_data(byteflow)

        # load img
        img = unpacked[0].numpy()
        # buf = six.BytesIO()
        # buf.write(imgbuf)
        # buf.seek(0)
        # img = Image.open(buf).convert('RGB')

        # load label
        target = unpacked[1].item()

        if self.transform is not None:
            img = self.transform(img)

        # im2arr = np.array(img)

        if self.target_transform is not None:
            target = self.target_transform(target)

        # return img, target
        return img, target

    def __len__(self):
        return len(self.imgs)

    def __repr__(self):
        return self.__class__.__name__ + ' (' + self.db_path + ')'

    # def __get_labels__(self):
 
