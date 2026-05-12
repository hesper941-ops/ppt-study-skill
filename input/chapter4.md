# Chapter 4 - Filtering in the Frequency Domain

## Slide 1
Title: Filtering in the Frequency Domain

## Slide 2
Outline:
1. Preliminary Concepts
2. Sampling and the Fourier Transform of Sampled Functions
3. The Discrete Fourier Transform (DFT) of One Variable
4. Extension to Functions of Two Variables
5. Some Properties of the 2-D Discrete Fourier Transform
6. The Basics of Filtering in the Frequency Domain
7. Image Smoothing Using Frequency Domain Filters
8. Image Sharpening Using Frequency Domain Filters
9. Selective Filtering

## Knowledge Block 1 - Some Properties of the 2-D DFT

### Slide 3
Relationships Between Spatial and Frequency Intervals
The separations between samples in the frequency domain are inversely proportional to both the spacing between spatial samples and the number of samples.
2-D DFT and 2-D IDFT.

### Slide 4
Separability
The 2-D DFT can be obtained by computing the 1-D transform of each row and then computing the 1-D transform along each column of the result.

### Slide 5
Translation and Rotation
Use polar coordinates.
Rotating f(x,y) by an angle rotates F(u,v) by the same angle, and vice versa.

### Slide 6
Translation
Multiplying f(x,y) by (-1)^(x+y) is equivalent to shifting the origin of the DFT to the center of the frequency rectangle.

### Slide 7
Periodicity
DFT is infinitely periodic in u and v directions.
The image obtained by inverse Fourier transform is also of infinite period.
DFT implementation only computes one cycle.

### Slide 8
Center of frequency rectangle
F(0,0) is moved to the center of the frequency rectangle.
Example: size 20 x 15 has center at (10,7) when counting from 0.

### Slide 9
Symmetry Properties
If f(x,y) is a real function:
- Fourier transform is conjugate symmetric with respect to the origin
- Fourier spectrum is symmetric with respect to the origin
- Real part is even
- Imaginary part is odd

### Slide 10
Fourier Spectrum and Phase Angle
F(u,v) is complex in general.
F(0,0) is the DC component.
It equals the sum of image intensities and corresponds to MN times the average gray value.
Power spectrum and phase angle are introduced.

### Slide 11
Visual Examples: Spectrum

### Slide 12
Visual Examples: Spectrum
Examples of rotated rectangle and translation in spectrum.

### Slide 13
Visual Examples: Phase Angle

### Slide 14
Visual Examples: Reconstruction
Only phase reconstruction
Only spectrum reconstruction
Phase + partial spectrum
Spectrum + partial phase

### Slide 15
Visual example:
Analyze the corresponding spectrum of the image.

### Slide 16
The 2-D Convolution Theorem
Convolution theorem:
Spatial domain convolution filtering is equivalent to frequency domain product filtering.
2-D circular convolution.

### Slide 17
Wraparound error
The convolution itself is periodic because of DFT periodicity.
When periods are close, they interfere and cause wraparound error.

### Slide 18
Solution to wraparound error
Zero padding.
Choose padded size large enough to avoid wraparound.

### Slide 19
Circular convolution in 2-D case
To eliminate wraparound error: padding zeros.
Appending zeros may create discontinuities.
In frequency domain this is analogous to convolution with sinc.

### Slide 20
Frequency Leakage
Finite-length truncation introduces extra frequency components not originally present.
Energy leaks into neighboring frequencies.
This can produce blocky effects.
Leakage cannot be totally eliminated.
Reducing leakage: windowing.

## Knowledge Block 2 - The Basics of Filtering in the Frequency Domain

### Slide 21
Frequency Domain Filtering Fundamentals
Filtering in frequency domain consists of modifying the Fourier transform and then computing the inverse transform.
g(x,y) = inverse Fourier transform of H(u,v)F(u,v)

### Slide 22
Convolution theorem and enhancement map
Steps:
1. Compute image DFT
2. Choose transfer function H(u,v)
3. Modify spectrum
4. Perform inverse DFT
Pre-process: padding
Post-process: de-padding, take real part, truncate to [0,255]
If only rough visual analysis is needed, padding may be skipped.

### Slide 23
Results using different frequency domain filters.

### Slide 24
Example of Gaussian low-pass filtering
Comparison of periodicity without padding and after padding.

### Slide 25
Zero-phase-shift filters
Filters that affect real and imaginary parts equally and thus have no effect on phase.
These are the filters considered in this chapter.

### Slide 26
Small changes in the phase angle can have dramatic and usually undesirable effects.

### Slide 27
Summary of Steps for Filtering in the Frequency Domain

### Slide 28
Summary of Steps for Filtering in the Frequency Domain

### Slide 29
Correspondence Between Filtering in the Spatial and Frequency Domains
Impulse response h(x,y) corresponds to transfer function H(u,v).
Frequency lowpass filter -> smoothing filter
Frequency highpass filter -> sharpening filter
Selective filters: band reject/pass, notch reject/pass

### Slide 30
Advantage of frequency filters: easy to interpret
Advantage of spatial filters: small masks for speed and implementation
One way to combine both:
Specify in frequency domain, compute IDFT, then design small spatial masks.

### Slide 31
Correspondence examples
Gaussian filter
Difference of Gaussians (DoG)

## Knowledge Block 3 - Image Smoothing Using Frequency Domain Filters

### Slide 32
Ideal Lowpass Filters (ILPF)
All frequencies inside a circle of radius D0 pass without attenuation.
Frequencies outside are completely filtered out.
D(u,v) is the distance from the frequency center.

### Slide 33
ILPF visualization
Perspective plot
Filter image
Radial cross section
Cutoff frequency definition

### Slide 34
Image smoothing using ILPF
Calculate percentage of image power inside radius D0.

### Slide 35
ILPF results with different cutoff frequencies
As cutoff radius increases, less power is filtered out and blur decreases.
Ringing may appear.

### Slide 36
ILPF explanation
Blurred image from lowpass filtering.
Ringing effect appears near edges.

### Slide 37
Butterworth Lowpass Filter (BLPF)
Transfer function of n-order BLPF.
Compared with ILPF, BLPF has no sharp discontinuity at D0.
When D = D0, H(u,v) = 0.5

### Slide 38
BLPF results
Ringing is generally imperceptible for order 2, but can become significant for higher order.

### Slide 39
Spatial representation of BLPF with different orders.

### Slide 40
Gaussian Lowpass Filter (GLPF)
Transfer function of GLPF.
When D(u,v) = D0, the filter value drops to 0.607 of its maximum.

### Slide 41
Inverse Fourier transform of a Gaussian is also Gaussian.
Therefore GLPF does not have ringing effect.

### Slide 42
GLPF results
GLPF has obvious blur effect and no ringing.
For the same cutoff frequency, GLPF gives slightly less smoothing than a 2nd-order BLPF.
BLPF offers tighter control but may introduce ringing.

### Slide 43
Summary of LPF

### Slide 44
Application of Lowpass Filter
Low-resolution text samples.
GLPF can connect broken character segments.

### Slide 45
Application examples of GLPF with different cutoff frequencies.

### Slide 46
Further application examples of GLPF with different cutoff frequencies.

## Knowledge Block 4 - Image Sharpening Using Frequency Domain Filters

### Slide 47
Highpass Filters
Image sharpening can be realized by highpass filtering.
Highpass transfer function can be obtained from lowpass filter:
H_hp(u,v) = 1 - H_lp(u,v)

### Slide 48
Ideal Highpass Filter (IHPF)
Sets to zero all frequencies inside radius D0 and passes all outside.
IHPF has ringing.

### Slide 49
Butterworth Highpass Filter (BHPF)
n-order BHPF.
Transition is smoother than IHPF.

### Slide 50
Gaussian Highpass Filter (GHPF)
Transfer function of GHPF.

### Slide 51
Summary of HPF
Ideal, Butterworth, and Gaussian highpass filters.

### Slide 52
Spatial representation of three highpass filters.

### Slide 53
Sharpening in Frequency Domain
Example using Butterworth highpass filter of order 4 with cutoff frequency 50.
Compare result of highpass filtering and thresholding.

### Slide 54
The Laplacian in Frequency Domain
Laplacian with 2-D Fourier transform.
Properties of Fourier transform.

### Slide 55
Laplacian in frequency domain
When origin is moved to the center of the frequency rectangle.
Laplacian filtered image and enhancement formula.

### Slide 56
Laplacian in frequency domain example.

### Slide 57
Unsharp Masking, Highboost Filtering, and High-Frequency-Emphasis Filtering
Unsharp masking: mask = original - lowpass result
Highboost filtering: k > 1
High-frequency emphasis filtering is introduced.

### Slide 58
Examples:
Chest X-ray image
Butterworth highpass result
High-frequency-emphasis filtering
Histogram equalization result

### Slide 59
Homomorphic Filtering
An image can be expressed as illumination component times reflectance component.
Illumination varies slowly.
Reflectance varies abruptly at object boundaries.
Goal: dynamic range compression and contrast enhancement.

### Slide 60
Homomorphic filtering steps
Logarithm
DFT
Filtering
Inverse DFT
Exponential

### Slide 61
Homomorphic filter transfer function can attenuate low-frequency illumination and amplify high-frequency reflectance.

### Slide 62
Example of image enhancement with homomorphic filtering.

## Knowledge Block 5 - Selective Filtering

### Slide 63
Bandreject and Bandpass Filters
Reject or pass frequencies in a predefined neighborhood about the center of the frequency rectangle.

### Slide 64
Notch Filter
Notch reject filter must work symmetrically.
Zero-phase-shift filters must be symmetric about the origin.
Butterworth notch reject filter of order n.

### Slide 65
Notch Filter example.

### Slide 66
Notch Pass Filter
Complementary with notch reject filter.

### Slide 67
Notch Pass Filter example.

## Slide 68
Summary of this Chapter
Preliminary concepts
Sampling theorem
Aliasing
1-D DFT
2-D extension
2-D sampling theorem
Aliasing in images
2-D DFT and IDFT
Properties of 2-D DFT

## Slide 69
Summary of this Chapter
Basics of filtering in the frequency domain
Steps for filtering
Correspondence between spatial and frequency filtering
Lowpass filters: ideal, Butterworth, Gaussian
Highpass filters: ideal, Butterworth, Gaussian
Laplacian in frequency domain
Homomorphic filtering
Selective filtering: band reject/pass, notch reject/pass
