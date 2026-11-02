# Case Studies

To complement the aggregate evaluation, we examine three manually audited
examples that illustrate different levels of graph usefulness: a successful
case (`q0115`), a partially successful case (`q0140`), and a failure case
(`q0003`). These examples are not intended to establish clinical correctness;
rather, they show how topic matching and OPM path structure affect
explainability.

## Successful Case: q0115

**sample_id.** `q0115`

**Question summary.** The case describes an older patient with exertional
dyspnea and chest pressure, a crescendo-decrescendo systolic murmur, delayed
radial pulses, left ventricular hypertrophy, and a thick calcified aortic
valve. The question asks for the area of the stenotic aortic valve using
Doppler-derived flow measurements.

**Matched topic.** `aortic stenosis`

**Key OPM path.** Valve calcification -> aortic valve narrowing -> left
ventricular outflow obstruction -> pressure overload -> exertional
dyspnea/chest pressure.

**Interpretation.** This is a high-relevance graph: the matched topic is the
central diagnosis, and the OPM path captures the clinically salient mechanism
of calcific valve narrowing, impaired left ventricular outflow, and pressure
loading. The path is therefore useful as an explanation scaffold for why the
case is organized around aortic stenosis.

**Limitation or observation.** The graph supports the disease mechanism but
does not encode the quantitative continuity-equation step needed to compute the
exact valve area. Thus, the graph is explanatory for topic relevance and
mechanism, while the final numerical calculation still depends on external
formula knowledge.

## Partially Successful Case: q0140

**sample_id.** `q0140`

**Question summary.** The case describes fever, Roth spots, painless palmar
lesions, splinter hemorrhages, mitral valve vegetations, and gram-positive
bacteria compatible with a bile-tolerant, salt-intolerant organism. The
question asks what additional condition should be considered in addition to
endocarditis.

**Matched topic.** `infective endocarditis`

**Key OPM path.** Microorganisms -> microbial adhesion -> infected valve
surface; heart valve -> vegetation formation -> valve vegetation -> infective
endocarditis. A parallel branch links endocardium -> platelet-fibrin deposition
-> valve dysfunction.

**Interpretation.** The graph is topically relevant and explains the observed
endocarditis findings: microorganisms adhere to a valve surface, vegetations
form, and the resulting valve involvement supports the matched topic. This
makes the graph useful for explaining the visible clinical syndrome.

**Limitation or observation.** The explanatory path is incomplete for the
actual question target. The case also tests the association between
Streptococcus gallolyticus/bovis bacteremia and colorectal neoplasia, but the
graph remains focused on endocarditis morphology and valve pathology. This is
therefore a partially successful answer-graph alignment case: the graph
explains the endocarditis syndrome but not the downstream organism-disease
association needed to support the question-specific answer.

## Failure Case: q0003

**sample_id.** `q0003`

**Question summary.** The case describes a neonate whose mother had fever,
rash, myalgias, and lymphadenopathy during early pregnancy, with abnormal
retinal findings on neonatal examination. The question asks which congenital
heart defect is most likely.

**Matched topic.** `pulmonary embolism`

**Key OPM path.** Venous thrombus -> thrombus embolization -> reduced pulmonary
perfusion -> pulmonary embolism. Additional branches link pulmonary artery ->
pulmonary artery obstruction -> right heart strain and right ventricle ->
ventilation-perfusion mismatch -> hypoxemia.

**Interpretation.** The OPM path is internally coherent for pulmonary embolism,
but it is not relevant to the neonatal congenital-infection scenario. The graph
models an acquired thromboembolic process rather than a prenatal infectious
mechanism leading to congenital cardiac abnormalities.

**Limitation or observation.** This case illustrates a topic-mismatch failure.
The matched graph may be structurally valid, but structural validity does not
guarantee case-level explainability. Because the selected topic is unrelated to
the key diagnostic mechanism, the graph provides little support for reasoning
about the likely congenital heart defect. A more appropriate graph would
represent congenital rubella infection and its association with congenital
cardiac defects such as patent ductus arteriosus.

Together, these cases support the aggregate findings. When topic matching is
accurate, the generated OPM graph can serve as a useful explanation scaffold.
When the topic is only partially aligned, the graph may explain visible cardiac
findings but fail to support the question-specific answer. When topic matching
fails, structural graph validity alone is insufficient for case-level
explainability.
