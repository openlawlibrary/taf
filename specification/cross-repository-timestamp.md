# Cross-Repository Timestamp Implementation

This document serves as an extension to the specifications of The Archive Framework (TAF),
tailored to apply its mechanisms for the maintenance and protection of digital law repositories.
While the foundational design of TAF is agnostic to the nature of the content it protects,
the following discussion is dedicated to describing the use-case specific considerations
for the secure long-term storage, update, and retrieval of legal documentation.

## [1. Intro](#1-intro)

TAF is already in use by some governments to protect their legal documents after
they are published. However, in the context of legal documents, it is crucial to consider
a time scale that spans not just years, but decades and even centuries. The data
published today by governments must remain accessible and verifiable far into the future,
akin to how we preserve and access centuries-old books in libraries. For instance, with
printed law, we can verify the authenticity of an official seal and ensure no pages are
missing or altered, even in copies of works that are hundreds of years old.

Translating this level of trust and verification to digital data presents a unique
and significant challenge. In the digital realm, the preservation and validation of legal
documents over extended periods present complex challenges. This complexity is heightened
when considering the range of potential events that could occur over such a lengthy time
frame. These include natural disasters, technological advancements that could enable
attackers to exploit current algorithm vulnerabilities, and  the possibility of
governments abandoning their digital law repositories.

### [1.1 Background](#11-background)

The Archive Framework (TAF) is a framework that applies The Update Framework (TUF)
to Git repositories. It does not aim to enhance the security features of Git or a
hosting platform like GitHub. Instead, TAF provides a more secure update process
based on TUF metadata stored in a separate Git repository.

In essence, the Git repository, known as the authentication or TAF repository, stores
information about the Git repositories under its protection. This includes details like
repository names and a list of URLs from which they can be downloaded, as well as valid commit
SHAs. However, this authentication repository is more than just a standard Git repository; it
also functions as a TUF (The Update Framework) repository. This means that the repository
information is stored in target and metadata files, conforming to the TUF specification.
In order to update these files, it is necessary to sign them using a threshold of keys, as
required by the TUF specification. While the use of hardware keys is not a mandatory
requirement within TAF, the framework is compatible with and encourages the use of YubiKeys
for enhanced security.

One of the most critical components in TAF is its updater, which is intended to be used in place
of the manual execution of git clone or pull commands. The updater's first task is to validate the
authentication repository, a process that involves invoking TUF's updater. Subsequently, based on
the data stored in the authentication repository, the updater validates other referenced Git
repositories. If this validation process encounters no errors, all repositories will be cloned or
updated. Conversely, if any issue is detected within the authentication repository, or if there is
a discrepancy between the actual commit history and the information retrieved from the
authentication repository, the update process will be halted. In such instances, the user will be
notified of the detected validation issue. This ensures that if a malicious actor managed to push
changes to one of the protected repositories, users would not inadvertently pull down these
compromised updates.

This system is designed to provide a level of protection that surpasses what is typically offered
by code hosting platforms like GitHub and GitLab. There are several reasons why relying solely on
these platforms is not adequate, particularly for repositories owned by governments, which are
frequent targets of malicious actors. An attacker could, for instance, gain access to an
individual's personal computer, compromise their GitHub account, or even breach GitHub itself.
Subsequently, they might push new commits or alter the commit history of repositories.
However, even if an attacker succeeds in pushing to the authentication repository, any
modifications made to the TUF metadata and target files would be detected by the updater if they
are not correctly signed. In scenarios where YubiKeys are utilized for signing, an attacker would
face the significant challenge of physically obtaining a threshold of these devices, a task made
even more difficult if the keys are distributed across various geographical locations.

### [1.2 Problem](#12-problem)

Verifying that a set of repositories is valid according to the information stored
in the corresponding authentication repository is meaningful only when there's a
strong reason to trust that the authentication repository itself was published by
a credible source. To illustrate this point with an analogy, consider a guitar
tuned to itself. While it may produce a harmonious sound, it could still be out
of tune when compared to a standard pitch. In a similar manner, a set of repositories
might appear internally consistent and valid based on their contained data. However,
there's a possibility that they could have been set up by an attacker to emulate
officially published repositories.

This potential vulnerability highlights the need for additional security mechanisms
beyond internal consistency checks. In essence, it of crucial importance to establish a
reliable method for confirming that an authentication repository has indeed been published
and maintained by the expected party.

Moreover, it is essential to maintain access to verifiable digital law, particularly
in scenarios where the government, originally responsible for publishing the documents,
is no longer interested or capable of maintaining the repository. This situation calls
for a verification process that can operate independently of the original publisher.

Additionally, when considering a time scale that far exceeds the typical lifespan of
software solutions, there are several other challenges that must be addressed.
Periodically, the tech community witnesses the discovery of security vulnerabilities in
algorithms that were once deemed robust. It is reasonable to assume that such discoveries
will continue to impact hash algorithms and asymmetric cryptography, which are essential
for updating authentication repositories. A notable example is SHA-1, a 'secure hash
algorithm' in use since 1995, which was compromised in 2017 – merely 22 years after its
inception.

Another significant challenge arises from catastrophic events such as natural disasters,
which could result in the complete loss of signing keys. The framework must have strategies
for recovery from such occurrences. These recovery mechanisms will also be discussed in the
upcoming sections

## [2. Leveraging trust in institutions and out-of-band authentication](#2-leveraging-trust-in-institutions-and-out-of-band-authentication)

By utilizing the TAF updater, any interested party has the capability to validate and
clone the authentication repository, as well as all referenced repositories that may
contain digital law in various formats. It is crucial to recognize that while TAF does not
inherently require repositories to be publicly accessible, the specific goal of making
legal documents publicly and freely accessible does necessitate their public availability.
As a result, it is feasible for anyone to create local copies of these repositories for
each government that uses TAF for their digital law storage.

While having multiple copies of government-published repositories forms a part of the
solution to the aforementioned problems, there are several critical questions that need to
be addressed:

- How does one verify the authenticity of a repository before initiating the TAF updater?
- When relying on the existence of multiple copies, what can ensure faith in the
validity of these local copies? Which external actors can be deemed trustworthy?
- How can the repository verification process be executed independently of the original
publisher's involvement?"

The resolution to the first question involves the repository's maintainer verifying the
validity of a specific commit of the authentication repository. By doing so, they attest
that they are indeed the original publishers. Often, this commit is the initial one.
However, this approach leads to a another question: How will the maintainer actually
convey this information? The proposed idea is to require direct communication with the
publisher, for instance, via a phone call. While the publication of this information on a
website may appear more convenient, the potential for website hacking significantly
compromises the security advantages of the while process. Once the validity of one
particular commit is confirmed, TAF's updater can then be used to validate all subsequent
commits. For clarity in our discussion, we will refer to the commit SHA, obtained through
these out-of-band mechanisms, as the 'out-of-band commit'.

To address the second question, the fundamental idea is to engage reputable
institutions such as libraries, universities, and archives. Drawing an analogy to how
law libraries hold printed copies of legal documents, these institutions can be
instrumental in hosting digital, freely accessible law repositories in our digitally
evolving era. Similar to how they manage physical books from different governments,
they could host digital versions of law repositories from various governmental sources.

Before hosting these digital repositories, reputable institutions would engage in out-of-band
authentication, a vital step to avoid unintentionally endorsing repositories that may have
been created or compromised by malicious actors. Beyond merely storing local copies of
government-published repositories, these institutions are also envisioned to establish their
own authentication repositories. In these repositories, they would store the out-of-band
commits for each digital law repository they have verified and downloaded. This method forms
the groundwork for a system that operates independently of continuous government involvement.
Furthermore, by periodically running the TAF updater, these institutions can ensure that their local copies remain in sync with the original, or upstream, repositories.

It is important to note that, although human and technical errors are always a possibility,
the framework operates under the assumption of good faith regarding internal employees of
these institutions. TAF should provide tools for these institutions to detect human and
technical errors as well as compromises in their own or other trusted institutions'
repositories. These compromises can then be handled out of band. The discussion of these
tools, however, falls beyond the scope of this specification.

That being said, the overarching objective is to involve as many reputable institutions as
possible. These institutions are expected to conduct out-of-band authentication and
substantiate the authenticity and timeliness of digital law repositories, whether published
by a government or another institution. Ideally, there should be instances of overlap, where
multiple institutions independently validate the same digital law repository.

This framework does not create a traditional web of trust as commonly understood. In a
typical web of trust, trust is transitive: if person A trusts person B, and person B trusts
person C, then person A may also choose to trust person C. However, in our scenario, we
depend on institutions independently affirming the authenticity and timeliness of a
repository. Thus, the trust is not extended beyond the immediate connection, with the depth
of trust limited to just one layer.

Within this network, participating institutions will be able to compare data related to digital law
repositories they host. This comparative analysis is conducted after the institutions have completed
out-of-band authentication and utilized the TAF updater to clone their local versions of the
government's digital law repositories. Such a process enables the detection of any invalid copies that
might be circulating within this trusted network. For instance, this system can uncover scenarios where
an institution has, perhaps unknowingly, cloned a repository fork that was illicitly created by an
attackerThe finer details regarding the specific workings of this process fall beyond the scope of this
overview.

The integration of reputable institutions, which establish their own authentication repositories and
store out-of-band commits, offers significant advantages. This setup enables interested parties to
approach these institutions to acquire an out-of-band commit, crucial for verifying the authenticity of
a specific digital law repository. However, the benefits extend beyond this direct interaction.

A single authentication repository maintained by an institution can attest to the authenticity of
multiple digital law repositories published by various governments. This means that an interested
party, by confirming the authenticity of the institution's repository, can gain access to all
out-of-band commits for the repositories monitored by that institution. Such a strategy aligns with our
aim of engaging multiple institutions, leading to a more evenly distributed workload across a wider
network. Furthermore, the establishment of this robust network of trust provides an opportunity to
automate the initial, moderate-security out-of-band authentication process. This could be achieved
through a collective agreement among all institutions that have validated a repository's authenticity.

## [3. Recovery strategies](#3-recovery-strategies)

As previously highlighted, given the extensive time scale spanning decades and centuries, we must
prepare for the possibility of various disasters and attacks. This section will focus on the measures
and protocols that can be enacted in response to such eventualities. It is important to note that this
discussion assumes that the web of trusted institutions, as described earlier, has already been
established.

### [3.1 Disaster recovery](#31-disaster-recovery)

Even when a government is actively maintaining their authentication repository, unforeseen
catastrophic events, such as natural disasters, could lead to the loss of all signing keys. In the
event of such a calamity, the government can start a new authentication repository
and sign the metadata using the new keys. However, this would render the previous out-of-band authentication
performed by attesting institutions outdated. Despite this, these institutions would be highly
motivated to promptly update their attestations. This ensures they can keep receiving
authenticated updates.

In other scenarios where key rotation is necessary, the TUF framework provides comprehensive
guidelines to handle such situations. This process can be executed without the need to establish a
new repository, and it does not require attesting institutions to update their out-of-band data.
By following TUF's specified procedures, an existing digital law repository can continue to be
validated and trusted.

### [3.2 Handling discovery of vulnerabilities in hash algorithms and asymmetric cryptography](#32-handling-discovery-of-vulnerabilities-in-hash-algorithms-and-asymmetric-cryptography)

Note - this is based on my understanding of how could cross-repository timestamp work. I might have
misunderstood some details. If this does not make sense, David should review when available.

Given the extensive time frame of decades and centuries that we are considering for maintaining
accessibility to legal data, changes in secure hash algorithms are inevitable. The TUF specification
mandates that all targets metadata files store hashes of the target files, ensuring that clients can
verify their integrity. The snapshot metadata file, in turn, records the version number
of the targets metadata file, as well as that of the root metadata file. The timestamp metadata
file then stores the hash of the snapshot metadata file, facilitating a quick check for updates.

Similarly, in considering the long-term implications for digital law repositories, it's essential
to acknowledge potential vulnerabilities in asymmetric cryptography.
Take, for example, a digital law repository where the keys were generated in 2020 using a specific key
generation method, denoted as method X. Fast forward a decade, numerous updates to the digital law have
been made, and a security flaw is discovered in method X. This flaw potentially compromises the first n
commits, as they were signed with keys generated by the now-vulnerable method X.

If a government is still maintaining its digital law repository, it can create hashes using new and
secure algorithms or execute key rotation and sign. That means that, going forward, an attacker would
not be able to exploit these vulnerabilities. However, they would still be able to attack commits
predating these updates and create their fork of a digital law repository.

In the event that an attacker has created such a fork of an authentication repository, where the first
n commits mirror those of the official repository, distinguishing between the two solely based on the
out-of-band commit SHA becomes impossible if this commit is among these first n commits. To counteract
this issue, the institutions, which periodically execute the TAF updater to synchronize with new
changes, must preserve additional metadata.

Following each successful update detected by the TAF updater, these institutions should record the
latest validated commit of the updated digital law repository. If an attacker introduces new commits
to a forked repository, comparing the information from the trusted institutions' authentication
repositories with that of these forks can reveal any discrepancies. This method is also effective in
identifying cases where an attacker creates a fork to create the illusion of a lack of updates.

Moreover, institutions should engage in cross-validation with other institutions in the network. This
involves comparing their records of digital law repositories, not just the initial out-of-band
commits, but also the most recent commits they have pulled. This cross-validation process can detect
divergences in the event a malicious fork is mistakenly accepted by a trusted institution. The system
would not expect all institutions to have the same latest commit; the latest validated commit of an
institution whose copy is older is expected to be in the list of all authenticatable commits of other
institutions.

### [3.3 Governments abandoning their digital law repositories](#33-governments-abandoning-their-digital-law-repositories)

Considering the long-term perspective, where legal data must remain accessible for decades or
even centuries, it can be assumed that some governments may eventually abandon their digital law
repositories. In these situations, the out-of-band authentication previously conducted by
various institutions becomes essential. Even in the absence of direct support from the
original government publisher, users can still approach these institutions. Having already
validated the repository's authenticity and retrieved the out-of-band data, they can continue
supplying this information, ensuring that interested parties maintain the ability to
authenticate and access the legal content they need.

Further questions arise from the possibility of repositories being abandoned. While a government is
actively involved in maintaining a repository, the plan is for institutions to monitor that specific
repository, the one under the government's care. In this scenario, the government's repository can be
considered the original, and the copies held by trusted institutions are essentially mirrors. It's
important to note, however, that these trusted institutions do store additional data about a government's
digital law repository and maintain a record of the update history, albeit separately from their mirrored
copy. This leads to a crucial question: How can institutions determine when a government is no longer
actively maintaining their digital law repository

Consider a scenario where a government publishes a final update, marked by a capstone, indicating it as the
official end-of-life for the repository. This capstone signifies that the repository will not be updated
beyond this point. However, years down the line, the hash and signing algorithms used to create this final
commit might become vulnerable due to advancements in technology or cryptographic research. Conversely,
there’s also the possibility of a government abandoning their repository without providing such an
end-of-life marker. In either case, the responsibility to ascertain whether a repository is no longer
active or updatable falls to the trusted institutions within the network. These institutions must
accurately identify and record this final update. Consequently, if any copy of the repository within the
web of institutions displays updates beyond this recorded final version, it should be flagged as invalid.

Another critical issue to address is the eventual obsolescence of hashing and signing algorithms used
during the creation of the last update of the original repository. We already have precedents like SHA-1,
which, despite currently being deemed unsafe, still requires substantial computational resources and costs
to exploit its weaknesses. However, in a decade, exploiting such vulnerabilities might become significantly
easier. This scenario poses a risk particularly when a government ceases to maintain their repository.
If a government ceases to maintain their repository, it will remain perpetually vulnerable due to the
obsolescence of hashing and signing algorithms However, in cases where an institution ceases to monitor
the original repository — recognizing that it has been abandoned — and if an attacker subsequently
compromises this repository, such malicious activities will not be reflected in the institution's mirrored copy.

However, the previous conclusion doesn't completely address all potential concerns. With a large number of
copies of an abandoned repository, each lacking security updates, we are faced with significant questions:
What actions could an attacker feasibly undertake in such a scenario, and how might these actions affect
the entire network of repositories? Additionally, if discrepancies arise, how do we determine which
institutions' copies have remained untampered with? It's also crucial to understand the methods
institutions will use to keep track of all updates made while the repositories were actively maintained.
This leads to another fundamental question: How can we be confident in the security of this information?

## [4. Example](#4-example)

(Needs to be extended)

Let's say the following:

- City of San Mateo, City of Baltimore, and District of Columbia all manage their own
repositories, each containing their respective laws and legal documents.
- University of Wisconsin Law Library and New York University Law Library, acting as
secondary, validating entities, clone the aforementioned repositories, perform
out-of-band authentication to ensure validity, and then create their respective repositories.
- In creating their own repositories, Wisconsin and New York universities will add an
additional layer of security and redundancy. By doing so, they validate the information
and protect against the potential discontinuation of the primary repositories managed by
the governments.
- Future entities or individuals seeking to authenticate these digital law repositories
can cross-verify the data between Wisconsin and New York. Consistency between these
secondary repositories would imply that the data has remained intact and authentic since
the last update from the primary governmental repositories.
- In the event that any of the governmental entities (e.g., San Mateo, Baltimore, DC)
cease to maintain their repositories, the data, having been preserved by Wisconsin and
New York, remains available and authenticated up until the last point of update.

In practical application, it's recommended to engage more entities than merely Wisconsin
and New York, as discrepancies could arise between even trustworthy sources. Expanding
the network to involve a multitude of actors enhances the system's reliability and resilience.
