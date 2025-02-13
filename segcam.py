import argparse
import cv2
import numpy as np
import torch
import torch.nn
from torchvision import models
import matplotlib.pyplot as plt

from pytorch_grad_cam import GradCAM, \
                             ScoreCAM, \
                             GradCAMPlusPlus, \
                             AblationCAM, \
                             XGradCAM, \
                             EigenCAM, \
                             EigenGradCAM

from pytorch_grad_cam.utils.roi import BaseROI, \
                                    PixelROI, \
                                    ClassROI, \
                                    get_output_tensor, \
                                    SegModel

from pytorch_grad_cam import GuidedBackpropReLUModel
from pytorch_grad_cam.utils.image import show_cam_on_image, \
                                         deprocess_image, \
                                         preprocess_image


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--use-cuda', action='store_true', default=False,
                        help='Use NVIDIA GPU acceleration')
    parser.add_argument('--image-path', type=str, default='./examples/both.png',
                        help='Input image path')
    parser.add_argument('--aug_smooth', action='store_true',
                        help='Apply test time augmentation to smooth the CAM')
    parser.add_argument('--eigen_smooth', action='store_true',
                        help='Reduce noise by taking the first principle componenet'
                        'of cam_weights*activations')
    parser.add_argument('--method', type=str, default='gradcam',
                        choices=['gradcam', 'gradcam++', 'scorecam', 'xgradcam',
                                 'ablationcam', 'eigencam', 'eigengradcam'],
                        help='Can be gradcam/gradcam++/scorecam/xgradcam'
                             '/ablationcam/eigencam/eigengradcam')
    parser.add_argument('--roimode', type=int, default='0')
    args = parser.parse_args()
    args.use_cuda = args.use_cuda and torch.cuda.is_available()
    if args.use_cuda:
        print('Using GPU for acceleration')
    else:
        print('Using CPU for computation')

    return args


if __name__ == '__main__':
    """ python cam.py -image-path <path_to_image>
    Example usage of loading an image, and computing:
        1. CAM
        2. Guided Back Propagation
        3. Combining both
    """

    args = get_args()
    methods = \
        {"gradcam": GradCAM,
         "scorecam": ScoreCAM,
         "gradcam++": GradCAMPlusPlus,
         "ablationcam": AblationCAM,
         "xgradcam": XGradCAM,
         "eigencam": EigenCAM,
         "eigengradcam": EigenGradCAM}

    model = models.segmentation.fcn_resnet50(pretrained=True)
    model.eval()
    # Choose the target layer you want to compute the visualization for.
    # Usually this will be the last convolutional layer in the model.
    # Some common choices can be:
    # Resnet18 and 50: model.layer4[-1]
    # VGG, densenet161: model.features[-1]
    # mnasnet1_0: model.layers[-1]
    # You can print the model to help chose the layer
    target_layer = model.backbone.layer4[-1]

    rgb_img = cv2.imread(args.image_path, 1)[:, :, ::-1]
    rgb_img = np.float32(rgb_img) / 255
    input_tensor = preprocess_image(rgb_img, mean=[0.485, 0.456, 0.406], 
                                             std=[0.229, 0.224, 0.225])

    ROIMode = args.roimode
    if ROIMode == 0:
        ## All pixels
        segmodel = SegModel(model, roi=BaseROI(rgb_img))
    elif ROIMode == 1:
        ## Single code assigned roi
        roi = PixelROI(50, 130, rgb_img)
        segmodel = SegModel(model, roi=roi)
    elif ROIMode == 2:
        ## User pick a pixel
        roi = PixelROI(50, 130, rgb_img)
        ## Before or after pass to model, both work
        # roi.pickPoint()
        segmodel = SegModel(model, roi=roi)
        roi.pickPixel()
    elif ROIMode == 3:
        ## Of specific class (GT or predict, depending on what user passes)
        pred = torch.argmax(get_output_tensor(model(input_tensor)), -3).squeeze(0)
        roi = ClassROI(rgb_img, pred, 12)
        # roi.largestComponent()
        # roi.smallestComponent()
        # roi.pickClass()
        roi.pickComponentClass()
        segmodel = SegModel(model, roi=roi)


    cam = methods[args.method](model=segmodel,
                               target_layer=target_layer,
                               use_cuda=args.use_cuda)

    # If None, returns the map for the highest scoring category.
    # Otherwise, targets the requested category.
    target_category = None

    # AblationCAM and ScoreCAM have batched implementations.
    # You can override the internal batch size for faster computation.
    cam.batch_size = 32

    grayscale_cam = cam(input_tensor=input_tensor,
                        target_category=target_category,
                        aug_smooth=args.aug_smooth,
                        eigen_smooth=args.eigen_smooth)

    # Here grayscale_cam has only one image in the batch
    grayscale_cam = grayscale_cam[0, :]

    cam_image = show_cam_on_image(rgb_img, grayscale_cam)

    gb_model = GuidedBackpropReLUModel(model=segmodel, use_cuda=args.use_cuda)
    gb = gb_model(input_tensor, target_category=target_category)

    cam_mask = cv2.merge([grayscale_cam, grayscale_cam, grayscale_cam])
    cam_gb = deprocess_image(cam_mask * gb)
    gb = deprocess_image(gb)

    if True:
        plt.figure()
        plt.imshow(cam_image)
        # plt.figure()
        # plt.imshow(gb)
        plt.figure()
        plt.imshow(cam_gb)
        plt.show()
    else:
        cv2.imwrite(f'{args.method}_cam.jpg', cam_image)
        cv2.imwrite(f'{args.method}_gb.jpg', gb)
        cv2.imwrite(f'{args.method}_cam_gb.jpg', cam_gb)
