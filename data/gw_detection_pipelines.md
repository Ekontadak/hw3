# Gravitational Wave Detection Pipelines: From Raw Strain to Astrophysical Inference

> Source: compiled from the primary pipeline papers listed in the References section.
> Author (curator): [Eftychios Kontadakis]

---

## 1. Overview

Detecting a gravitational wave requires a multi-stage software pipeline that
transforms raw interferometer strain data into confident astrophysical detections
and inferred source parameters. The pipeline divides into four broad stages:
data conditioning, matched-filter search, candidate significance estimation, and
Bayesian parameter estimation [1, 2, 5].

---

## 2. Data Conditioning

Before any search is run, the raw strain data h(t) from each interferometer must
be conditioned [1].

**Calibration.** The raw photodetector output is converted into a calibrated strain
time series using a frequency-dependent response function that accounts for the
optical and mechanical properties of the interferometer [1].

**Data quality vetoes.** Real detectors are not perfectly stationary or Gaussian.
Transient noise artifacts — called *glitches* — contaminate the data and can mimic
astrophysical signals. Data quality investigations characterise detector data into
three general classes: (i) data polluted enough to be discarded without searching,
(ii) data that can be filtered but whose candidate events in poor-quality intervals
should be vetoed, and (iii) data suitable for astrophysical searches [2].

**Power spectral density estimation.** The noise power spectral density (PSD)
S_n(f) characterises the noise floor as a function of frequency. The PSD is used
to whiten the data and is central to the matched-filter calculation [2].

---

## 3. Matched Filtering: The Core Detection Principle

The central technique for detecting compact binary coalescences (CBCs) is matched
filtering [2]. The signal-to-noise ratio (SNR) ρ(t) is defined using an inner
product in the frequency domain. For two waveforms s and h, the inner product is:

    (s|h)(t) = 4 Re ∫ [s̃(f) h̃*(f) / S_n(f)] e^{2πift} df          [2]

The SNR for a template with two orthogonal phases h_cos and h_sin is then:

    ρ²(t) = [(s|h_cos)² + (s|h_sin)²] / (h_cos|h_cos)               [2]

This weighting by S_n(f) is optimal in the sense that, for stationary Gaussian
noise and a known signal waveform, no other linear filter achieves a higher
expected SNR [2]. In practice, real detector data contains non-stationary noise
and non-Gaussian transients, so additional steps are required to mitigate noise
transients and accurately assess statistical significance [2].

---

## 4. The Template Bank

Since the signal waveform parameters are not known in advance, the pipeline filters
data against a large *template bank*: a pre-computed discrete grid of waveforms
spanning the astrophysically relevant parameter space of compact binary systems [2].

In the PyCBC pipeline, the bank is generated so that the loss in matched-filter
SNR due to the discrete nature of the bank is no more than **3%** for any signal
in the target parameter space [2]. The exact placement of templates depends on
the detector's noise PSD S_n(f), and a single fixed bank is used to filter data
from all detectors in the network [2].

Waveform approximants used to generate templates — such as IMRPhenomD,
SEOBNRv4, and TaylorF2 — are implemented in **LALSuite**, the central software
library for waveform models used in Advanced LIGO and Advanced Virgo analyses
[2, 4].

---

## 5. Active Search Pipelines

Several matched-filter pipelines operate in parallel on LVK data, running in both
low-latency (near real-time) and offline modes.

### 5.1 PyCBC

PyCBC is an open-source Python toolkit for gravitational wave data analysis [2].
Its search pipeline performs matched filtering in the frequency domain. The
pipeline was used in the first Advanced LIGO observing run (O1) and
unambiguously identified two binary black hole mergers, GW150914 and
GW151226 [2].

Key features of PyCBC [2]:

- **Exact-match coincidence.** The same template must produce a trigger above
  threshold in multiple detectors within the light-travel-time window between
  sites. The intrinsic parameters — masses and spins — of triggers from each
  detector must be exactly the same.
- **χ² signal consistency test.** To distinguish genuine signals from noise
  transients, the pipeline computes partial SNRs in p disjoint frequency bands
  and checks whether they are distributed as expected for a real signal. Glitches
  typically fail this test even when they produce high SNR.
- **Re-weighted SNR.** The raw SNR is re-weighted by the χ² statistic to produce
  a refined ranking statistic that is more robust to non-Gaussian noise.
- **Background estimation via time slides.** False-alarm rates are estimated
  empirically by time-shifting triggers from different detectors by more than the
  light-travel time, generating large amounts of background noise coincidences
  against which candidates are ranked. The pipeline can measure false-alarm rates
  as low as one per million years [2].

### 5.2 GstLAL

GstLAL (GStreamer + LIGO Algorithm Library) is a stream-based matched-filter
pipeline designed to detect gravitational waves within approximately one minute
of the arrival of the merger signal at Earth [3]. It connects the GStreamer
multimedia framework with LAL routines to enable near-real-time processing.
Analysts using the low-latency mode of this pipeline were the first to identify
GW151226, the second gravitational-wave event ever detected [3].

Key features of GstLAL [3, 4]:

- **Singular value decomposition (SVD).** The LLOID (Low Latency Online Inspiral
  Detection) method compresses waveform templates into an orthogonal basis via
  SVD, enabling efficient time-domain matched filtering across a large template
  bank at manageable computational cost [3].
- **Time-domain SNR computation.** GstLAL computes the SNR in the time domain,
  in contrast to PyCBC's frequency-domain approach [3].
- **Likelihood ratio ranking statistic.** Candidates are ranked using a
  multi-dimensional likelihood ratio that incorporates per-detector SNR, signal
  consistency tests, time-averaged detector sensitivity, and comparison against
  modelled signal and noise populations [3, 4].
- **Early-warning search.** By accumulating SNR from only the inspiral portion
  of the signal, GstLAL can issue alerts approximately **10–60 seconds before the
  merger** of a low-redshift binary neutron star system, enabling electromagnetic
  observatories to begin follow-up before the event peaks [4].

### 5.3 MBTA

The Multi-Band Template Analysis (MBTA) pipeline is a low-latency coincident
analysis pipeline for the detection of gravitational waves from compact binary
coalescences [5]. During the third LIGO-Virgo observing run (O3), MBTA
contributed to 42 alerts with a **median latency of 36 seconds** [5].

The defining feature of MBTA is its computational strategy: to reduce the cost
of matched filtering, the pipeline splits the matched filter across two (or more)
frequency bands [5]. The boundary frequency f_c between the low-frequency and
high-frequency bands is selected so that the SNR is shared roughly equally
between them — typically f_c ≈ 100 Hz for advanced detectors [5]. On average,
this procedure loses negligible SNR compared to a single-band matched filter [5].
The two bands are then coherently recombined when a sufficiently high SNR is
detected to produce a unified single-detector trigger [5].

---

## 6. Candidate Significance: The False-Alarm Rate

A high SNR in a single detector is not sufficient for a detection claim. The
pipeline must demonstrate that the candidate is unlikely to have arisen from
noise alone. This is quantified by the **false-alarm rate (FAR)**: the expected
rate of noise events with a ranking statistic equal to or greater than the
candidate's [2].

In PyCBC, FARs are estimated empirically by generating a large background of
noise coincidences via time slides [2]. The significance of a candidate is also
expressed as **p_astro**: the posterior probability that the event is of
astrophysical origin, which has become standard reporting in the GWTC catalogs [6].

---

## 7. Parameter Estimation: Bayesian Inference

Once a candidate event is identified, a separate suite of codes performs full
Bayesian inference to characterise the astrophysical source. Given the observed
data d, the posterior probability distribution over source parameters θ is:

    p(θ | d) ∝ p(d | θ) · p(θ)                                       [7, 8]

where p(d | θ) is the likelihood — evaluated by computing the match between the
data and a template waveform at parameters θ, weighted by the noise PSD — and
p(θ) is the prior. Because the parameter space is high-dimensional (approximately
15 parameters for a precessing binary), sampling requires dedicated stochastic
samplers [7, 8].

### 7.1 LALInference

LALInference was the primary parameter estimation framework used through
GWTC-1 [7]. It implements Markov chain Monte Carlo (MCMC) and nested sampling
algorithms within the LALSuite infrastructure, and was used to produce the
published posterior samples for all events in the first two observing runs [7, 8].

### 7.2 Bilby

Bilby is a modular Bayesian inference library designed to extend and eventually
replace LALInference [8]. Written in Python, it separates the sampler,
likelihood, prior, and waveform model into independent components that can be
exchanged freely. Bilby has been validated against LALInference results on
GWTC-1 events, with maximum Jensen-Shannon divergence between posteriors of
0.0026 nat — consistent with sampling noise [8].

Key design features of Bilby [8]:

- Supports arbitrary waveform approximants via LALSuite integration.
- Enables tidal deformability inference for binary neutron star events.
- Modular architecture allows extension to new source models, detectors, and
  likelihoods.
- Provides straightforward syntax accessible to non-expert users, while
  maintaining expert-level PE infrastructure.

---

## References

[1] J. Aasi et al. (LIGO Scientific Collaboration), "Advanced LIGO," *Class.
Quantum Grav.* **32**, 074001 (2015). arXiv:1411.4547

[2] S. A. Usman et al., "The PyCBC search for gravitational waves from compact
binary coalescence," *Class. Quantum Grav.* **33**, 215004 (2016).
arXiv:1508.02357

[3] C. Messick et al., "Analysis framework for the prompt discovery of compact
binary mergers in gravitational-wave data," *Phys. Rev. D* **95**, 042001 (2017).
arXiv:1604.04324

[4] S. Sachdev et al., "The GstLAL search analysis methods for compact binary
mergers in Advanced LIGO's second and Advanced Virgo's first observing runs,"
(2019). arXiv:1901.08580

[5] F. Aubin et al., "The MBTA pipeline for detecting compact binary coalescences
in the third LIGO-Virgo observing run," *Class. Quantum Grav.* **38**, 095004
(2021). arXiv:2012.11512

[6] R. Abbott et al. (LIGO Scientific, Virgo, KAGRA), "GWTC-3: Compact binary
coalescences observed by LIGO and Virgo during the second part of the third
observing run," (2021). arXiv:2111.03606

[7] J. Veitch et al., "Parameter estimation for compact binaries with ground-based
gravitational-wave observations using the LALInference software library," *Phys.
Rev. D* **91**, 042003 (2015). arXiv:1409.7215

[8] G. Ashton et al., "BILBY: A user-friendly Bayesian inference library for
gravitational-wave astronomy," *Astrophys. J. Suppl.* **241**, 27 (2019).
arXiv:1811.02042
